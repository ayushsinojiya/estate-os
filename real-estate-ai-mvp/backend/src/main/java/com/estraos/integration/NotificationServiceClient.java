package com.estraos.integration;

import java.util.Map;

public interface NotificationServiceClient {
    Map<String, Object> send(Map<String, Object> request);
}
