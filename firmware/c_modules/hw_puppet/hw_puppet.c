#include "hw_puppet.h"

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
