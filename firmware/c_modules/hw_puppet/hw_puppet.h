#ifndef HW_PUPPET_H
#define HW_PUPPET_H

#include <stddef.h>
#include <stdbool.h>

#define _HW_PUPPET_STR(x) #x
#define _HW_PUPPET_XSTR(x) _HW_PUPPET_STR(x)

#ifdef HW_PUPPET_VERSION_RAW
#define HW_PUPPET_VERSION_STR _HW_PUPPET_XSTR(HW_PUPPET_VERSION_RAW)
#elif !defined(HW_PUPPET_VERSION_STR)
#define HW_PUPPET_VERSION_STR "0.3.0-dev"
#endif

#ifdef HW_PUPPET_GIT_HASH_RAW
#define HW_PUPPET_GIT_HASH_STR _HW_PUPPET_XSTR(HW_PUPPET_GIT_HASH_RAW)
#elif !defined(HW_PUPPET_GIT_HASH_STR)
#define HW_PUPPET_GIT_HASH_STR "unknown"
#endif

#ifndef HW_PUPPET_BUILD_DATE_STR
#define HW_PUPPET_BUILD_DATE_STR __DATE__ " " __TIME__
#endif

#ifndef HW_PUPPET_PLATFORM_STR
#define HW_PUPPET_PLATFORM_STR "ESP32-S3"
#endif

#define HW_PUPPET_BADGE_MAX_LEN 64

const char *hw_puppet_version_string(void);
const char *hw_puppet_git_hash(void);
const char *hw_puppet_build_date(void);
const char *hw_puppet_platform(void);

// Persistent hardware badge (stored in ESP-IDF NVS)
bool hw_puppet_get_badge(char *buf, size_t max_len);
bool hw_puppet_set_badge(const char *badge);

#endif // HW_PUPPET_H
