package com.estraos.integration;

/** Never contains provider body, URL, bearer key, customer data or original cause. */
public final class ExternalServiceException extends RuntimeException {
    private final String service;
    private final String code;
    private final int status;

    public ExternalServiceException(String service, String code, int status, String message) {
        super(message);
        this.service = service;
        this.code = code;
        this.status = status;
    }

    public String getService() { return service; }
    public String getCode() { return code; }
    public int getStatus() { return status; }
}
