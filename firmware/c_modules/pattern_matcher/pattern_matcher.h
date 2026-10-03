#ifndef PATTERN_MATCHER_H
#define PATTERN_MATCHER_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PATTERN_MATCHER_MAX_TRIGGERS 8
#define PATTERN_MATCHER_MAX_PATTERN  64
#define PATTERN_MATCHER_MAX_REPLY    32

typedef void (*pattern_match_cb_t)(int slot_id, const char *pattern, void *user_data);
typedef int  (*pattern_match_reply_fn_t)(const uint8_t *data, size_t len, void *user_ctx);

/**
 * Initialize the pattern matcher engine.
 */
void pattern_matcher_init(void);

/**
 * Configure output callback used to transmit auto-replies.
 */
void pattern_matcher_set_reply_writer(pattern_match_reply_fn_t fn, void *user_ctx);

/**
 * Process a chunk of incoming stream data through all active triggers (O(1) per byte).
 */
void pattern_matcher_process_bytes(const uint8_t *data, size_t len);

/**
 * Register a pattern trigger.
 * Returns slot_id (0..7) on success, or -1 if all slots are in use.
 */
int  pattern_matcher_register_trigger(const char *pattern, size_t pat_len,
                                      const char *reply, size_t rep_len,
                                      bool once, uint32_t cooldown_ms,
                                      bool case_sensitive,
                                      pattern_match_cb_t cb, void *user_data);

/**
 * Cancel and deactivate a specific trigger slot.
 */
bool pattern_matcher_cancel_trigger(int slot_id);

/**
 * Clear and disarm all active triggers.
 */
void pattern_matcher_clear_all_triggers(void);

/**
 * Check if a trigger slot is currently active.
 */
bool pattern_matcher_trigger_is_active(int slot_id);

/**
 * Synchronous helper: blocks caller until pattern is matched or timeout expires.
 */
bool pattern_matcher_wait_for(const char *pattern, size_t pat_len,
                              const char *reply, size_t rep_len,
                              uint32_t timeout_ms, bool case_sensitive);

#ifdef __cplusplus
}
#endif

#endif // PATTERN_MATCHER_H
