FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package
FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S estraos && adduser -S estraos -G estraos
WORKDIR /app
COPY --from=build --chown=estraos:estraos /app/target/estraos-api-1.0.0.jar app.jar
USER estraos
EXPOSE 8080
ENTRYPOINT ["java","-jar","app.jar"]
