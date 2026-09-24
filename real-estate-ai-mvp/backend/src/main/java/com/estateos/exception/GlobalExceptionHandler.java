package com.estateos.exception;

import java.time.Instant;
import java.util.*;
import org.slf4j.*;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class GlobalExceptionHandler {
  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  public static Map<String, Object> body(int status, String code, String message, Object details) {
    return Map.of(
        "timestamp",
        Instant.now().toString(),
        "status",
        status,
        "code",
        code,
        "message",
        message,
        "details",
        details);
  }

  @ExceptionHandler(ApiException.class)
  ResponseEntity<?> api(ApiException e) {
    return ResponseEntity.status(e.status).body(body(e.status, e.code, e.getMessage(), Map.of()));
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  ResponseEntity<?> validation(MethodArgumentNotValidException e) {
    Map<String, String> details = new LinkedHashMap<>();
    e.getBindingResult()
        .getFieldErrors()
        .forEach(
            x ->
                details.put(
                    x.getField(), Objects.toString(x.getDefaultMessage(), "Invalid value")));
    return ResponseEntity.badRequest()
        .body(body(400, "VALIDATION_ERROR", "Request validation failed", details));
  }

  @ExceptionHandler({
    IllegalArgumentException.class,
    HttpMessageNotReadableException.class,
    MethodArgumentTypeMismatchException.class,
    MissingRequestHeaderException.class
  })
  ResponseEntity<?> malformed(Exception e) {
    return ResponseEntity.badRequest()
        .body(
            body(
                400,
                "VALIDATION_ERROR",
                "Invalid request value or missing workspace header",
                Map.of()));
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  ResponseEntity<?> conflict(Exception e) {
    return ResponseEntity.status(409)
        .body(
            body(
                409,
                "CONFLICT",
                "A duplicate record or invalid related reference conflicts with this request",
                Map.of()));
  }

  @ExceptionHandler(jakarta.validation.ConstraintViolationException.class)
  ResponseEntity<?> constraint(Exception e) {
    return ResponseEntity.badRequest()
        .body(
            body(
                400,
                "VALIDATION_ERROR",
                "IDs must be positive and request parameters must meet validation rules",
                Map.of()));
  }

  @ExceptionHandler(com.estateos.integration.ExternalServiceException.class)
  ResponseEntity<?> external(com.estateos.integration.ExternalServiceException e) {
    return ResponseEntity.status(e.getStatus())
        .body(body(e.getStatus(), e.getCode(), e.getMessage(), Map.of("service", e.getService())));
  }

  @ExceptionHandler(Exception.class)
  ResponseEntity<?> unknown(Exception e) {
    log.error("Request failed: {}", e.getClass().getSimpleName());
    return ResponseEntity.internalServerError()
        .body(body(500, "INTERNAL_ERROR", "Unable to complete request", Map.of()));
  }
}
