package com.estraos.exception;

public class ApiException extends RuntimeException {
  public final int status;
  public final String code;

  public ApiException(int status, String code, String message) {
    super(message);
    this.status = status;
    this.code = code;
  }

  public static ApiException bad(String message) {
    return new ApiException(400, "VALIDATION_ERROR", message);
  }

  public static ApiException missing() {
    return new ApiException(404, "NOT_FOUND", "Resource not found in this workspace");
  }

  public static ApiException forbidden() {
    return new ApiException(403, "FORBIDDEN", "You do not have access to this action or workspace");
  }

  public static ApiException conflict(String message) {
    return new ApiException(409, "CONFLICT", message);
  }
}
