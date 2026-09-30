package com.estraos.repository;

import com.estraos.entity.UserAccount;
import java.util.*;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<UserAccount, Long> {
  Optional<UserAccount> findByEmailIgnoreCase(String email);
}
