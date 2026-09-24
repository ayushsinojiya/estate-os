FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package
FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S estateos && adduser -S estateos -G estateos
WORKDIR /app
COPY --from=build --chown=estateos:estateos /app/target/estateos-api-1.0.0.jar app.jar
USER estateos
EXPOSE 8080
ENTRYPOINT ["java","-jar","app.jar"]
