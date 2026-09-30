package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.dto.Requests;
import com.estraos.exception.ApiException;
import com.estraos.repository.UserRepository;
import com.estraos.security.TenantContext;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {
  private final UserRepository users;
  private final PasswordEncoder password;
  private final JwtEncoder encoder;
  private final JdbcTemplate db;
  private final TenantContext tenant;
  private final AuditService audit;
  private final long minutes;
  private final String dummyHash;

  public AuthService(
      UserRepository users,
      PasswordEncoder password,
      JwtEncoder encoder,
      JdbcTemplate db,
      TenantContext tenant,
      AuditService audit,
      @Value("${app.token-minutes}") long minutes) {
    this.users = users;
    this.password = password;
    this.encoder = encoder;
    this.db = db;
    this.tenant = tenant;
    this.audit = audit;
    if (minutes < 5 || minutes > 1440)
      throw new IllegalStateException("JWT_TOKEN_MINUTES must be between 5 and 1440");
    this.minutes = minutes;
    this.dummyHash = password.encode(java.util.UUID.randomUUID().toString());
  }

  public List<Map<String, Object>> workspaces(Long user) {
    return db.query(
        "SELECT w.id,w.name,w.demo,r.name AS role FROM workspaces w JOIN workspace_members m ON"
            + " w.id=m.workspace_id JOIN roles r ON r.id=m.role_id WHERE m.user_id=? ORDER BY w.id",
        (rs, n) ->
            Map.of(
                "id",
                rs.getString("id"),
                "name",
                rs.getString("name"),
                "role",
                rs.getString("role"),
                "demo",
                rs.getBoolean("demo")),
        user);
  }

  public Map<String, Object> me() {
    Long id = tenant.user();
    var u =
        users
            .findById(id)
            .orElseThrow(() -> new ApiException(401, "UNAUTHORIZED", "User unavailable"));
    return Map.of(
        "user",
        Map.of("id", u.id.toString(), "name", u.name, "email", u.email),
        "workspaces",
        workspaces(id));
  }

  @Transactional
  public Map<String, Object> login(Requests.Login request) {
    var u = users.findByEmailIgnoreCase(request.email().trim());
    boolean matches =
        password.matches(request.password(), u.map(x -> x.passwordHash).orElse(dummyHash));
    if (u.isEmpty() || !matches || !u.get().enabled)
      throw new ApiException(401, "INVALID_CREDENTIALS", "Email or password is incorrect");
    var user = u.get();
    Instant now = Instant.now(), expires = now.plusSeconds(minutes * 60);
    Long session =
        db.queryForObject(
            "INSERT INTO auth_sessions(user_id,expires_at) VALUES (?,?) RETURNING id",
            Long.class,
            user.id,
            java.sql.Timestamp.from(expires));
    var claims =
        JwtClaimsSet.builder()
            .issuer("estraos")
            .subject(user.id.toString())
            .id(session.toString())
            .issuedAt(now)
            .expiresAt(expires)
            .build();
    String token =
        encoder
            .encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims))
            .getTokenValue();
    var workspaces = workspaces(user.id);
    for (var ws : workspaces)
      audit.record(Long.valueOf(ws.get("id").toString()), user.id, "LOGIN", "USER", user.id);
    return Map.of(
        "token",
        token,
        "expiresAt",
        expires.toString(),
        "user",
        Map.of("id", user.id.toString(), "name", user.name, "email", user.email),
        "workspaces",
        workspaces);
  }

  @Transactional
  public void logout() {
    Long user = tenant.user(), session = tenant.session();
    db.update(
        "UPDATE auth_sessions SET revoked=true,updated_at=now() WHERE id=? AND user_id=?",
        session,
        user);
    for (var ws : workspaces(user))
      audit.record(Long.valueOf(ws.get("id").toString()), user, "LOGOUT", "USER", user);
  }

  public List<Map<String, Object>> members(Long ws) {
    tenant.require(ws);
    return db.query(
        "SELECT u.id,u.name,u.email,r.name AS role FROM users u JOIN workspace_members m ON"
            + " u.id=m.user_id JOIN roles r ON r.id=m.role_id WHERE m.workspace_id=? AND u.enabled"
            + " ORDER BY u.name",
        (rs, n) ->
            Map.of(
                "id",
                rs.getString("id"),
                "name",
                rs.getString("name"),
                "email",
                rs.getString("email"),
                "role",
                rs.getString("role")),
        ws);
  }
}
