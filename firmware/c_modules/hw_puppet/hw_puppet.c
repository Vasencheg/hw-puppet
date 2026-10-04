#include "hw_puppet.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "hw_puppet";
static const char *NVS_NAMESPACE = "hw_puppet";
static const char *NVS_KEY_BADGE = "badge";

const char *hw_puppet_version_string(void) {
    return HW_PUPPET_VERSION_STR;
}

const char *hw_puppet_git_hash(void) {
    return HW_PUPPET_GIT_HASH_STR;
}

const char *hw_puppet_build_date(void) {
    return HW_PUPPET_BUILD_DATE_STR;
}

const char *hw_puppet_platform(void) {
    return HW_PUPPET_PLATFORM_STR;
}

bool hw_puppet_get_badge(char *buf, size_t max_len) {
    if (!buf || max_len == 0) {
        return false;
    }
    buf[0] = '\0';

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        return false;
    }

    size_t required_size = max_len;
    err = nvs_get_str(handle, NVS_KEY_BADGE, buf, &required_size);
    nvs_close(handle);

    return (err == ESP_OK);
}

bool hw_puppet_set_badge(const char *badge) {
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS for badge write: %d", err);
        return false;
    }

    if (!badge || strlen(badge) == 0) {
        err = nvs_erase_key(handle, NVS_KEY_BADGE);
        if (err == ESP_ERR_NVS_NOT_FOUND) {
            err = ESP_OK;
        }
    } else {
        err = nvs_set_str(handle, NVS_KEY_BADGE, badge);
    }

    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);

    return (err == ESP_OK);
}
