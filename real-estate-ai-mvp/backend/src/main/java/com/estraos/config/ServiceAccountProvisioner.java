package com.estraos.config;

import java.util.List;
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Provisions the voice agent's service login.
 *
 * <p>The agent authenticates through {@code POST /api/v1/auth/login} exactly like a human
 * principal, so session revocation, workspace membership, role checks and audit attribution all
 * behave as they already do. Nothing in {@link com.estraos.security.SecurityConfig} or {@link
 * com.estraos.security.TenantContext} needed a bypass for machine callers.
 *
 * <p>Provisioning is skipped entirely unless both {@code app.service-account.email} and {@code
 * app.service-account.password} are configured.
 */
@Component
@org.springframework.core.annotation.Order(2)
public class ServiceAccountProvisioner implements ApplicationRunner {
  private static final org.slf4j.Logger log =
      org.slf4j.LoggerFactory.getLogger(ServiceAccountProvisioner.class);

  private final JdbcTemplate db;
  private final PasswordEncoder password;
  private final String email;
  private final String secret;
  private final Long workspace;
  private final String workspaceName;
  private final String adminEmails;

  public ServiceAccountProvisioner(
      JdbcTemplate db,
      PasswordEncoder password,
      @Value("${app.service-account.email:}") String email,
      @Value("${app.service-account.password:}") String secret,
      @Value("${app.service-account.workspace-id:0}") Long workspace,
      @Value("${app.service-account.workspace-name:}") String workspaceName,
      @Value("${app.service-account.admin-emails:}") String adminEmails) {
    this.db = db;
    this.password = password;
    this.email = email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
    this.secret = secret == null ? "" : secret;
    this.workspace = workspace;
    this.workspaceName = workspaceName == null ? "" : workspaceName.trim();
    this.adminEmails = adminEmails == null ? "" : adminEmails.trim();
  }

  @Override
  @Transactional
  public void run(ApplicationArguments args) {
    if (email.isBlank() || secret.isBlank()) {
      log.info("No service account configured; the voice agent cannot authenticate to this API");
      return;
    }
    if (secret.length() < 16 || secret.toLowerCase(Locale.ROOT).contains("replace"))
      throw new IllegalStateException(
          "SERVICE_ACCOUNT_PASSWORD must be at least 16 characters of real secret material");
    if (workspace == null || workspace <= 0)
      throw new IllegalStateException(
          "SERVICE_ACCOUNT_WORKSPACE_ID must be the positive ID of an existing workspace");
    ensureWorkspace();

    Long user =
        db.queryForObject(
            "INSERT INTO users(name,email,password_hash) VALUES (?,?,?) ON CONFLICT(email) DO"
                + " UPDATE SET password_hash=excluded.password_hash,enabled=true,updated_at=now()"
                + " RETURNING id",
            Long.class,
            "Voice agent service account",
            email,
            password.encode(secret));
    Long role =
        db.queryForObject(
            "INSERT INTO roles(name) VALUES ('MANAGER') ON CONFLICT(name) DO UPDATE SET"
                + " updated_at=now() RETURNING id",
            Long.class);
    db.update(
        "INSERT INTO workspace_members(workspace_id,user_id,role_id) VALUES (?,?,?) ON"
            + " CONFLICT(workspace_id,user_id) DO UPDATE SET role_id=excluded.role_id,"
            + " updated_at=now()",
        workspace,
        user,
        role);
    log.info("Service account {} provisioned as MANAGER of workspace {}", email, workspace);
    grantAdmins();
  }

  /**
   * Gives named people ADMIN access to the service workspace.
   *
   * <p>Without this the workspace the voice agent works in has no human member, so its projects,
   * leads and calls are invisible in the UI — the data is there, but nobody can open it. Only
   * existing users are granted; this never creates a login.
   */
  private void grantAdmins() {
    if (adminEmails.isBlank()) return;
    Long role =
        db.queryForObject(
            "INSERT INTO roles(name) VALUES ('ADMIN') ON CONFLICT(name) DO UPDATE SET"
                + " updated_at=now() RETURNING id",
            Long.class);
    for (String raw : adminEmails.split(",")) {
      String address = raw.trim().toLowerCase(Locale.ROOT);
      if (address.isBlank()) continue;
      List<Long> ids =
          db.queryForList(
              "SELECT id FROM users WHERE lower(email)=? AND enabled", Long.class, address);
      if (ids.isEmpty()) {
        log.warn("Cannot grant workspace access to {}: no such user", address);
        continue;
      }
      db.update(
          "INSERT INTO workspace_members(workspace_id,user_id,role_id) VALUES (?,?,?) ON"
              + " CONFLICT(workspace_id,user_id) DO UPDATE SET role_id=excluded.role_id,"
              + " updated_at=now()",
          workspace,
          ids.getFirst(),
          role);
      log.info("Granted {} ADMIN access to workspace {}", address, workspace);
    }
  }

  /**
   * A freshly provisioned database has no workspaces outside the demo profile, which would leave a
   * clean deployment with nothing for the service account to belong to. Create the configured
   * workspace when a name is supplied, then move the identity sequence past it so later
   * auto-generated workspace IDs cannot collide with the one we placed by hand.
   */
  private void ensureWorkspace() {
    Integer existing =
        db.queryForObject("SELECT count(*) FROM workspaces WHERE id=?", Integer.class, workspace);
    if (existing != null && existing == 1) return;
    if (workspaceName.isBlank())
      throw new IllegalStateException(
          "Service account workspace "
              + workspace
              + " does not exist; set SERVICE_ACCOUNT_WORKSPACE_NAME to create it on first boot");
    db.update(
        "INSERT INTO workspaces(id,name) VALUES (?,?) ON CONFLICT(id) DO NOTHING",
        workspace,
        workspaceName);
    db.queryForObject(
        "SELECT setval(pg_get_serial_sequence('workspaces','id'),"
            + " GREATEST((SELECT max(id) FROM workspaces), 1))",
        Long.class);
    log.info("Created workspace {} \"{}\" for the service account", workspace, workspaceName);
  }
}
