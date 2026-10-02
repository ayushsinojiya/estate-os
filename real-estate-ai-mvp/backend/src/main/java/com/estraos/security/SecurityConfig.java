package com.estraos.security;

import com.estraos.exception.GlobalExceptionHandler;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import java.nio.charset.StandardCharsets;
import java.util.*;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.*;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.*;

@Configuration
public class SecurityConfig {
  @Bean
  PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
  }

  private byte[] secret(String secret) {
    if (secret == null
        || secret.getBytes(StandardCharsets.UTF_8).length < 32
        || secret.toLowerCase().contains("replace"))
      throw new IllegalStateException(
          "JWT_SECRET must contain at least 32 bytes of random secret material");
    return secret.getBytes(StandardCharsets.UTF_8);
  }

  @Bean
  JwtEncoder jwtEncoder(@Value("${app.jwt-secret}") String value) {
    return new NimbusJwtEncoder(new ImmutableSecret<>(secret(value)));
  }

  @Bean
  JwtDecoder jwtDecoder(@Value("${app.jwt-secret}") String value) {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withSecretKey(new SecretKeySpec(secret(value), "HmacSHA256"))
            .macAlgorithm(MacAlgorithm.HS256)
            .build();
    decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer("estraos"));
    return decoder;
  }

  @Bean
  SecurityFilterChain security(
      HttpSecurity http, ObjectMapper mapper, CorsConfigurationSource corsConfigurationSource)
      throws Exception {
    http.csrf(c -> c.disable())
        // Wired explicitly: an empty cors() customizer resolves the source by the conventional
        // bean name, or by type only when exactly one candidate exists, and silently falls back to
        // rejecting every cross-origin request when neither holds.
        .cors(c -> c.configurationSource(corsConfigurationSource))
        .sessionManagement(c -> c.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    http.authorizeHttpRequests(
        a ->
            a.requestMatchers(HttpMethod.OPTIONS, "/**")
                .permitAll()
                .requestMatchers(
                    "/api/v1/auth/login",
                    // Signed by Meta (X-Hub-Signature-256), verified in the controller.
                    "/api/v1/webhooks/whatsapp",
                    "/actuator/health",
                    "/actuator/health/**",
                    "/swagger-ui.html",
                    "/swagger-ui/**",
                    "/v3/api-docs/**")
                .permitAll()
                .anyRequest()
                .authenticated());
    http.oauth2ResourceServer(
        o ->
            o.jwt(j -> {})
                .authenticationEntryPoint(
                    (req, res, e) -> {
                      res.setStatus(401);
                      res.setContentType("application/json");
                      mapper.writeValue(
                          res.getOutputStream(),
                          GlobalExceptionHandler.body(
                              401,
                              "UNAUTHORIZED",
                              "Authentication required or token invalid",
                              Map.of()));
                    }));
    http.exceptionHandling(
        e ->
            e.authenticationEntryPoint(
                    (req, res, ex) -> {
                      res.setStatus(401);
                      res.setContentType("application/json");
                      mapper.writeValue(
                          res.getOutputStream(),
                          GlobalExceptionHandler.body(
                              401, "UNAUTHORIZED", "Authentication required", Map.of()));
                    })
                .accessDeniedHandler(
                    (req, res, ex) -> {
                      res.setStatus(403);
                      res.setContentType("application/json");
                      mapper.writeValue(
                          res.getOutputStream(),
                          GlobalExceptionHandler.body(403, "FORBIDDEN", "Access denied", Map.of()));
                    }));
    return http.build();
  }

  @Bean
  CorsConfigurationSource corsConfigurationSource(@Value("${app.cors-origins}") String origins) {
    CorsConfiguration c = new CorsConfiguration();
    c.setAllowedOrigins(Arrays.stream(origins.split(",")).map(String::trim).toList());
    c.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    c.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Workspace-Id", "Idempotency-Key"));
    c.setMaxAge(3600L);
    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", c);
    return source;
  }
}
