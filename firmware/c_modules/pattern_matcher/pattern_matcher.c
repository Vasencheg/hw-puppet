#include "pattern_matcher.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/idf_additions.h"
#include <string.h>
#include <ctype.h>

typedef struct {
    char               pattern[PATTERN_MATCHER_MAX_PATTERN];
    uint8_t            pattern_len;
    uint8_t            curr_idx;
    uint8_t            kmp_next[PATTERN_MATCHER_MAX_PATTERN];
    char               reply[PATTERN_MATCHER_MAX_REPLY];
    uint8_t            reply_len;
    bool               active;
    bool               once;
    bool               case_sensitive;
    uint32_t           cooldown_ticks;
    uint32_t           last_trigger_tick;
    pattern_match_cb_t cb;
    void              *user_data;
} trigger_slot_t;

static trigger_slot_t triggers[PATTERN_MATCHER_MAX_TRIGGERS];
static portMUX_TYPE   triggers_spinlock = portMUX_INITIALIZER_UNLOCKED;

static pattern_match_reply_fn_t s_reply_writer = NULL;
static void                    *s_reply_writer_ctx = NULL;

static void compute_kmp_table(const char *pat, uint32_t len, uint8_t *next) {
    if (len == 0) return;
    next[0] = 0;
    uint32_t j = 0;
    for (uint32_t i = 1; i < len; i++) {
        while (j > 0 && pat[i] != pat[j]) {
            j = next[j - 1];
        }
        if (pat[i] == pat[j]) {
            j++;
        }
        next[i] = (uint8_t)j;
    }
}

void pattern_matcher_init(void) {
    taskENTER_CRITICAL(&triggers_spinlock);
    memset(triggers, 0, sizeof(triggers));
    taskEXIT_CRITICAL(&triggers_spinlock);
}

void pattern_matcher_set_reply_writer(pattern_match_reply_fn_t fn, void *user_ctx) {
    s_reply_writer = fn;
    s_reply_writer_ctx = user_ctx;
}

void pattern_matcher_process_bytes(const uint8_t *data, size_t len) {
    if (data == NULL || len == 0) return;

    for (size_t b = 0; b < len; b++) {
        char c = (char)data[b];
        for (int s = 0; s < PATTERN_MATCHER_MAX_TRIGGERS; s++) {
            if (!triggers[s].active) continue;

            char c_cmp = triggers[s].case_sensitive ? c : (char)tolower((unsigned char)c);

            while (triggers[s].curr_idx > 0 && c_cmp != triggers[s].pattern[triggers[s].curr_idx]) {
                triggers[s].curr_idx = triggers[s].kmp_next[triggers[s].curr_idx - 1];
            }
            if (c_cmp == triggers[s].pattern[triggers[s].curr_idx]) {
                triggers[s].curr_idx++;
                if (triggers[s].curr_idx == triggers[s].pattern_len) {
                    triggers[s].curr_idx = 0; // Reset for next match

                    // Debounce cooldown check
                    uint32_t now = xTaskGetTickCount();
                    if (triggers[s].cooldown_ticks > 0 && triggers[s].last_trigger_tick != 0) {
                        if ((now - triggers[s].last_trigger_tick) < triggers[s].cooldown_ticks) {
                            continue;
                        }
                    }
                    triggers[s].last_trigger_tick = now;

                    // Direct auto-reply if configured
                    if (triggers[s].reply_len > 0 && s_reply_writer != NULL) {
                        s_reply_writer((const uint8_t *)triggers[s].reply,
                                       triggers[s].reply_len,
                                       s_reply_writer_ctx);
                    }

                    // Callback notification
                    if (triggers[s].cb) {
                        triggers[s].cb(s, triggers[s].pattern, triggers[s].user_data);
                    }

                    if (triggers[s].once) {
                        triggers[s].active = false;
                    }
                }
            }
        }
    }
}

int pattern_matcher_register_trigger(const char *pattern, size_t pat_len,
                                     const char *reply, size_t rep_len,
                                     bool once, uint32_t cooldown_ms,
                                     bool case_sensitive,
                                     pattern_match_cb_t cb, void *user_data) {
    if (pattern == NULL || pat_len == 0 || pat_len > PATTERN_MATCHER_MAX_PATTERN) {
        return -1;
    }
    if (reply != NULL && rep_len > PATTERN_MATCHER_MAX_REPLY) {
        return -1;
    }

    int found_slot = -1;
    taskENTER_CRITICAL(&triggers_spinlock);
    for (int i = 0; i < PATTERN_MATCHER_MAX_TRIGGERS; i++) {
        if (!triggers[i].active) {
            found_slot = i;
            break;
        }
    }

    if (found_slot >= 0) {
        trigger_slot_t *slot = &triggers[found_slot];
        memset(slot, 0, sizeof(trigger_slot_t));
        slot->case_sensitive = case_sensitive;
        for (size_t i = 0; i < pat_len; i++) {
            slot->pattern[i] = case_sensitive ? pattern[i] : (char)tolower((unsigned char)pattern[i]);
        }
        slot->pattern_len = (uint8_t)pat_len;
        slot->curr_idx = 0;
        compute_kmp_table(slot->pattern, slot->pattern_len, slot->kmp_next);

        if (reply != NULL && rep_len > 0) {
            memcpy(slot->reply, reply, rep_len);
            slot->reply_len = (uint8_t)rep_len;
        }

        slot->once = once;
        slot->cooldown_ticks = pdMS_TO_TICKS(cooldown_ms);
        slot->last_trigger_tick = 0;
        slot->cb = cb;
        slot->user_data = user_data;
        slot->active = true;
    }
    taskEXIT_CRITICAL(&triggers_spinlock);

    return found_slot;
}

bool pattern_matcher_cancel_trigger(int slot_id) {
    if (slot_id < 0 || slot_id >= PATTERN_MATCHER_MAX_TRIGGERS) {
        return false;
    }
    taskENTER_CRITICAL(&triggers_spinlock);
    triggers[slot_id].active = false;
    triggers[slot_id].cb = NULL;
    triggers[slot_id].user_data = NULL;
    taskEXIT_CRITICAL(&triggers_spinlock);
    return true;
}

void pattern_matcher_clear_all_triggers(void) {
    taskENTER_CRITICAL(&triggers_spinlock);
    for (int i = 0; i < PATTERN_MATCHER_MAX_TRIGGERS; i++) {
        triggers[i].active = false;
        triggers[i].cb = NULL;
        triggers[i].user_data = NULL;
    }
    taskEXIT_CRITICAL(&triggers_spinlock);
}

bool pattern_matcher_trigger_is_active(int slot_id) {
    if (slot_id < 0 || slot_id >= PATTERN_MATCHER_MAX_TRIGGERS) {
        return false;
    }
    return triggers[slot_id].active;
}

// Synchronous wait helper
typedef struct {
    SemaphoreHandle_t sem;
    bool              matched;
} sync_wait_ctx_t;

static void sync_wait_cb(int slot_id, const char *pattern, void *user_data) {
    sync_wait_ctx_t *ctx = (sync_wait_ctx_t *)user_data;
    if (ctx && ctx->sem) {
        ctx->matched = true;
        xSemaphoreGive(ctx->sem);
    }
}

bool pattern_matcher_wait_for(const char *pattern, size_t pat_len,
                              const char *reply, size_t rep_len,
                              uint32_t timeout_ms, bool case_sensitive) {
    sync_wait_ctx_t ctx = {
        .sem = xSemaphoreCreateBinary(),
        .matched = false
    };
    if (!ctx.sem) return false;

    int slot = pattern_matcher_register_trigger(
        pattern, pat_len,
        reply, rep_len,
        true, 0,
        case_sensitive,
        sync_wait_cb, &ctx
    );
    if (slot < 0) {
        vSemaphoreDelete(ctx.sem);
        return false;
    }

    uint32_t elapsed = 0;
    while (elapsed < timeout_ms && !ctx.matched) {
        uint32_t slice = (timeout_ms - elapsed > 50) ? 50 : (timeout_ms - elapsed);
        if (xSemaphoreTake(ctx.sem, pdMS_TO_TICKS(slice)) == pdTRUE) {
            ctx.matched = true;
            break;
        }
        elapsed += slice;
    }

    pattern_matcher_cancel_trigger(slot);
    vSemaphoreDelete(ctx.sem);
    return ctx.matched;
}
