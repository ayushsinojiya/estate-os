package com.estateos.service;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ManagedFileServiceTest {
  @Test
  void acceptsSupportedExtensionsAndStripsTraversalFromNames() {
    assertTrue(ManagedFileService.isSupported("brochure.PDF"));
    assertTrue(ManagedFileService.isSupported("inventory.xlsx"));
    assertTrue(ManagedFileService.isSupported("photos.WEBP"));
    assertFalse(ManagedFileService.isSupported("payload.exe"));
    assertEquals("brochure.pdf", ManagedFileService.safeName("../../brochure.pdf"));
  }
}
