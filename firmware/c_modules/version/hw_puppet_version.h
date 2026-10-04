#ifndef HW_PUPPET_VERSION_H
#define HW_PUPPET_VERSION_H

#include <stddef.h>

#define _HW_PUPPET_STR(x) #x
#define _HW_PUPPET_XSTR(x) _HW_PUPPET_STR(x)

#ifdef HW_PUPPET_VERSION_RAW
#define HW_PUPPET_VERSION_STR _HW_PUPPET_XSTR(HW_PUPPET_VERSION_RAW)
#elif !defined(HW_PUPPET_VERSION_STR)
#define HW_PUPPET_VERSION_STR "0.1.0-dev"
#endif

#ifdef HW_PUPPET_GIT_HASH_RAW
#define HW_PUPPET_GIT_HASH_STR _HW_PUPPET_XSTR(HW_PUPPET_GIT_HASH_RAW)
#elif !defined(HW_PUPPET_GIT_HASH_STR)
#define HW_PUPPET_GIT_HASH_STR "unknown"
#endif

#ifndef HW_PUPPET_BUILD_DATE_STR
#define HW_PUPPET_BUILD_DATE_STR __DATE__ " " __TIME__
#endif

const char *hw_puppet_version_string(void);
const char *hw_puppet_git_hash(void);
const char *hw_puppet_build_date(void);

#endif // HW_PUPPET_VERSION_H
