#pragma once

#include <stdbool.h>
#include "esp_err.h"
#include "web_request.h"

void dashboard_auth_init(void);
bool dashboard_auth_is_configured(void);
bool dashboard_auth_is_remote(web_request_t *req);
bool dashboard_auth_check(web_request_t *req);
bool dashboard_auth_check_csrf(web_request_t *req);
esp_err_t dashboard_auth_login(web_request_t *req, const char *password, bool remember);
esp_err_t dashboard_auth_set_password(const char *current, const char *password);
esp_err_t dashboard_auth_logout(web_request_t *req);
