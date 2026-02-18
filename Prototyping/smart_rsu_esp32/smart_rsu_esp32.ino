#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <DHT.h>

/* ================= WIFI ================= */
const char* ssid = "Aditya";
const char* password = "12345678";

/* ================= SUPABASE ================= */
const char* SUPABASE_URL = "https://espyrwotmztzrevuprmo.supabase.co/rest/v1/accidents";
const char* SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVzcHlyd290bXp0enJldnVwcm1vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEzOTQwMzUsImV4cCI6MjA4Njk3MDAzNX0.Z9MACwrO5Lzj-O38J7bgffa3mKXVClwD4qZIFrzaEnk";

/* ================= UDP ================= */
WiFiUDP udp;
const unsigned int localPort = 5005;
const char* NEXT_HOP_IP = "192.168.137.158";
const unsigned int FORWARD_PORT = 5005;
char incomingPacket[2048];

/* ================= WEB SERVER ================= */
WebServer server(80);

/* ================= SENSORS ================= */
#define DHTPIN 4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

#define MQ135_PIN 34
#define LDR_PIN 35

/* ================= DASHBOARD VARIABLES ================= */
String vehicleID = "N/A";
String issueData = "No Emergency";
String latitudeData = "-";
String longitudeData = "-";
String envStatus = "-";

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi Connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  udp.begin(localPort);
  server.on("/", handleRoot);
  server.begin();

  dht.begin();

  testSupabaseConnection();   // 🔥 TEST CONNECTION ON START
}

/* ================= LOOP ================= */
void loop() {

  // 🔥 LIVE SENSOR MONITOR
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  int gas = analogRead(MQ135_PIN);
  int light = analogRead(LDR_PIN);

  Serial.print("Temp: "); Serial.print(temp);
  Serial.print(" | Hum: "); Serial.print(hum);
  Serial.print(" | Gas: "); Serial.print(gas);
  Serial.print(" | Light: "); Serial.println(light);

  handleUDP();
  server.handleClient();

  delay(2000);
}

/* ================= HANDLE UDP ================= */
void handleUDP() {
  int packetSize = udp.parsePacket();

  if (packetSize) {
    int len = udp.read(incomingPacket, sizeof(incomingPacket));
    if (len > 0) incomingPacket[len] = 0;

    Serial.println("Packet Received:");
    Serial.println(incomingPacket);

    parsePacket(incomingPacket);
  }
}

/* ================= PARSE + ENRICH ================= */
void parsePacket(char* packet) {

  StaticJsonDocument<2048> doc;
  DeserializationError error = deserializeJson(doc, packet);

  if (error) {
    Serial.println("JSON Parse Failed");
    return;
  }

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  int gasValue = analogRead(MQ135_PIN);
  int ldrValue = analogRead(LDR_PIN);

  doc["hop_trace"].add("RSU");

  JsonObject env = doc.createNestedObject("rsu_environment");
  env["temperature"] = temperature;
  env["humidity"] = humidity;
  env["air_quality"] = gasValue;
  env["light_level"] = ldrValue;

  if (gasValue > 2000 && temperature > 45) {
    envStatus = "Possible Fire Detected";
  } else if (ldrValue < 500) {
    envStatus = "Low Visibility Condition";
  } else {
    envStatus = "Normal Environment";
  }

  doc["environment_status"] = envStatus;

  vehicleID = String((const char*)doc["vehicle_id"]);
  issueData = String((const char*)doc["issue"]);
  latitudeData = String(doc["latitude"].as<float>(), 6);
  longitudeData = String(doc["longitude"].as<float>(), 6);

  String finalPacket;
  serializeJson(doc, finalPacket);

  Serial.println("Final JSON Sent:");
  Serial.println(finalPacket);

  udp.beginPacket(NEXT_HOP_IP, FORWARD_PORT);
  udp.print(finalPacket);
  udp.endPacket();

  sendToSupabase(finalPacket);
}

/* ================= SUPABASE FUNCTION ================= */
void sendToSupabase(String jsonData) {

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi Not Connected - Cannot Send to Supabase");
    return;
  }

  HTTPClient http;
  http.begin(SUPABASE_URL);

  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
  http.addHeader("Prefer", "return=minimal");

  int httpResponseCode = http.POST(jsonData);

  Serial.print("Supabase Response Code: ");
  Serial.println(httpResponseCode);

  if (httpResponseCode == 201) {
    Serial.println("Data Successfully Inserted Into Supabase ✅");
  } else {
    Serial.println("Supabase Insert Failed ❌");
    Serial.println(http.getString());
  }

  http.end();
}

/* ================= SUPABASE CONNECTION TEST ================= */
void testSupabaseConnection() {

  Serial.println("Testing Supabase Connection...");

  HTTPClient http;
  http.begin(SUPABASE_URL);

  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));

  int httpResponseCode = http.GET();

  Serial.print("Supabase Test Response: ");
  Serial.println(httpResponseCode);

  if (httpResponseCode == 200) {
    Serial.println("Supabase Connected Successfully ✅");
  } else {
    Serial.println("Supabase Connection Failed ❌");
  }

  http.end();
}

/* ================= WEB DASHBOARD ================= */
void handleRoot() {

  String html = "<html><head><meta http-equiv='refresh' content='3'>";
  html += "<style>body{font-family:Arial;background:#111;color:white;padding:20px}</style>";
  html += "</head><body>";

  html += "<h1 style='color:red;'>🚨 Smart RSU Dashboard</h1>";
  html += "<p><b>Vehicle ID:</b> " + vehicleID + "</p>";
  html += "<p><b>Issue:</b> " + issueData + "</p>";
  html += "<p><b>Latitude:</b> " + latitudeData + "</p>";
  html += "<p><b>Longitude:</b> " + longitudeData + "</p>";
  html += "<p><b>Environment Status:</b> " + envStatus + "</p>";

  html += "</body></html>";

  server.send(200, "text/html", html);
}
