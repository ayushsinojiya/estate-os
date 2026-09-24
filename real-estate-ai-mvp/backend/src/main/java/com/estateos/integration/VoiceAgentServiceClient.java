package com.estateos.integration;

import java.util.Map;

public interface VoiceAgentServiceClient {
    Map<String, Object> startOutboundCall(Map<String, Object> request);
    Map<String, Object> getCallDetails(Map<String, Object> request);
}
