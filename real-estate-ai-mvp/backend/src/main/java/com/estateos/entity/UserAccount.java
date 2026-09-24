package com.estateos.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "users")
public class UserAccount {
  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  public Long id;

  @Column(nullable = false)
  public String name;

  @Column(nullable = false, unique = true)
  public String email;

  @Column(name = "password_hash", nullable = false)
  public String passwordHash;

  public boolean enabled;

  protected UserAccount() {}
}
