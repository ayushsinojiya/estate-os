package com.estraos.security;

import com.estraos.exception.ApiException;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public class TenantContext {
  private final JdbcTemplate db;

  public TenantContext(JdbcTemplate db) {
    this.db = db;
  }

  public Long user() {
    var authentication = SecurityContextHolder.getContext().getAuthentication();
    if (authentication == null || !(authentication.getPrincipal() instanceof Jwt jwt))
      throw new ApiException(401, "UNAUTHORIZED", "Authentication required");
    Long user = Long.valueOf(jwt.getSubject());
    Long session = Long.valueOf(jwt.getId());
    Integer count =
        db.queryForObject(
            "SELECT count(*) FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.id=? AND"
                + " s.user_id=? AND NOT s.revoked AND s.expires_at>now() AND u.enabled",
            Integer.class,
            session,
            user);
    if (count == null || count != 1)
      throw new ApiException(401, "SESSION_REVOKED", "Session expired or logged out");
    return user;
  }

  public Long session() {
    user();
    return Long.valueOf(
        ((Jwt) SecurityContextHolder.getContext().getAuthentication().getPrincipal()).getId());
  }

  public String require(Long workspace) {
    if (workspace == null || workspace <= 0)
      throw ApiException.bad("Workspace ID must be positive");
    Long user = user();
    var roles =
        db.queryForList(
            "SELECT r.name FROM workspace_members m JOIN roles r ON r.id=m.role_id WHERE"
                + " m.workspace_id=? AND m.user_id=?",
            String.class,
            workspace,
            user);
    if (roles.isEmpty()) throw ApiException.forbidden();
    return roles.getFirst();
  }

  public void manage(Long workspace) {
    if (!Set.of("ADMIN", "MANAGER").contains(require(workspace))) throw ApiException.forbidden();
  }

  public void member(Long workspace, Long user) {
    if (user == null) return;
    Integer n =
        db.queryForObject(
            "SELECT count(*) FROM workspace_members m JOIN users u ON u.id=m.user_id JOIN roles r"
                + " ON r.id=m.role_id WHERE m.workspace_id=? AND m.user_id=? AND u.enabled AND"
                + " r.name='REAL_ESTATE_AGENT'",
            Integer.class,
            workspace,
            user);
    if (n == null || n != 1)
      throw ApiException.bad("Assigned agent must be an active member of this workspace");
  }
}
