"""Keep existing native HTTP fixtures testing the shared application handlers.

The transport adapter itself is exercised separately by test_direct_http2.py.
These substitutions only connect the new interface to the existing HTTP mocks.
"""
def native_source(source, tunnel='false'):
    import re
    for name, native in {
        'web_request_t': 'httpd_req_t', 'web_route_t': 'httpd_uri_t',
        'web_header': 'httpd_req_get_hdr_value_str',
        'web_query': 'httpd_req_get_url_query_str', 'web_recv': 'httpd_req_recv',
        'web_req_to_sockfd': 'httpd_req_to_sockfd',
        'web_set_header': 'httpd_resp_set_hdr', 'web_set_type': 'httpd_resp_set_type',
        'web_set_status': 'httpd_resp_set_status', 'web_send_err': 'httpd_resp_send_err',
        'web_sendstr': 'httpd_resp_sendstr', 'web_send_ref': 'httpd_resp_send',
        'web_send': 'httpd_resp_send',
        'web_accepts_gzip': 'compressed_asset_accepts_gzip',
        'web_send_identity': 'compressed_asset_send_identity',
        'web_register_handler': 'httpd_register_uri_handler',
    }.items():
        source = re.sub(r'\b' + name + r'\b', native, source)
    source = source.replace('web_request_is_tunnel(req)', '(' + tunnel + ')')
    # Preserve the original fixture's response capture and ownership check.
    source = re.sub(r'(?m)^(\s*)web_send_owned\(req,\s*json\);',
                    r'\1httpd_resp_sendstr(req, json); free(json);', source)
    source = source.replace('web_send_owned(req, json)', '({ int sent = httpd_resp_sendstr(req, json); free(json); sent; })')
    source = source.replace('web_send_owned(req,json)', '({ int sent = httpd_resp_sendstr(req,json); free(json); sent; })')
    return source
