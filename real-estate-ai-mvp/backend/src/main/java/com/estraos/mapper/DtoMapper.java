package com.estraos.mapper;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class DtoMapper {
  private final ObjectMapper json;

  public DtoMapper(ObjectMapper json) {
    this.json = json;
  }

  public Map<String, Object> map(Object value) {
    return json.convertValue(value, new TypeReference<LinkedHashMap<String, Object>>() {});
  }

  public String write(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalArgumentException("Invalid JSON", e);
    }
  }

  public Map<String, Object> read(String value) {
    try {
      return json.readValue(value, new TypeReference<LinkedHashMap<String, Object>>() {});
    } catch (Exception e) {
      throw new IllegalStateException("Invalid stored JSON", e);
    }
  }
}
