package com.estraos.controller;

import com.estraos.mapper.DtoMapper;
import com.estraos.service.WhatsAppService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Meta WhatsApp Cloud API webhook: the subscription handshake (GET) and delivery statuses (POST).
 * Unauthenticated by necessity; every POST must carry a valid X-Hub-Signature-256 computed with
 * the app secret over the exact request body.
 */
@RestController
@RequestMapping("/api/v1/webhooks/whatsapp")
public class WhatsAppWebhookController {
  private final WhatsAppService whatsapp;
  private final DtoMapper mapper;
  private final String appSecret;
  private final String verifyToken;

  public WhatsAppWebhookController(WhatsAppService whatsapp, DtoMapper mapper,
      @Value("${app.whatsapp.app-secret:}") String appSecret,
      @Value("${app.whatsapp.verify-token:}") String verifyToken) {
    this.whatsapp = whatsapp;
    this.mapper = mapper;
    this.appSecret = appSecret;
    this.verifyToken = verifyToken;
  }

  @GetMapping
  public ResponseEntity<String> verify(@RequestParam(name = "hub.mode", required = false) String mode,
      @RequestParam(name = "hub.verify_token", required = false) String token,
      @RequestParam(name = "hub.challenge", required = false) String challenge) {
    if (verifyToken.isBlank() || !"subscribe".equals(mode) || token == null
        || !MessageDigest.isEqual(token.getBytes(StandardCharsets.UTF_8), verifyToken.getBytes(StandardCharsets.UTF_8)))
      return ResponseEntity.status(403).build();
    return ResponseEntity.ok(challenge == null ? "" : challenge);
  }

  static String signature(String secret, byte[] body) {
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
      return "sha256=" + HexFormat.of().formatHex(mac.doFinal(body));
    } catch (Exception e) {
      throw new IllegalStateException("HMAC unavailable", e);
    }
  }

  @PostMapping
  public ResponseEntity<Map<String, Object>> statuses(
      @RequestHeader(name = "X-Hub-Signature-256", required = false) String signature,
      @RequestBody byte[] body) {
    if (appSecret.isBlank() || signature == null
        || !MessageDigest.isEqual(signature.getBytes(StandardCharsets.UTF_8),
            signature(appSecret, body).getBytes(StandardCharsets.UTF_8)))
      return ResponseEntity.status(401).body(Map.of("status", 401, "code", "INVALID_SIGNATURE"));
    int updated = whatsapp.onStatusWebhook(mapper.read(new String(body, StandardCharsets.UTF_8)));
    return ResponseEntity.ok(Map.of("updated", updated));
  }
}
