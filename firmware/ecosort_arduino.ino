/*
  EcoSort - Arduino UNO firmware.

  Receives high-level command strings from the Raspberry Pi over USB serial
  at 9600 baud and translates them into PWM motor signals, servo positions,
  and ultrasonic obstacle checks.

  Hardware:
    - L298N motor driver -> 2x VEX 393 motors (rear wheels)
    - 3x HC-SR04 ultrasonic sensors (left 45 deg, center, right 45 deg)
    - 2x DS3225 servos (scoop arm)

  Commands accepted from Pi:
    FWD          - drive forward at full speed
    FWD_SLOW     - drive forward slowly (approach mode)
    STOP         - stop both motors
    TURN_L       - rotate left in place
    TURN_R       - rotate right in place
    SCOOP_DOWN   - lower scoop to ground
    SCOOP_UP     - raise scoop to bin position

  Messages sent to Pi:
    BLOCKED      - obstacle detected within stop threshold
    OK           - command acknowledged

  Author: Adam Gosine
  NYU Tandon EG-UY 1004 - Spring 2026
*/

#include <Servo.h>
#include <NewPing.h>

// ---------------------------------------------------------------------------
// Pin definitions
// ---------------------------------------------------------------------------

// L298N motor driver
const int ENA = 5;     // PWM speed for motor A
const int IN1 = 6;
const int IN2 = 7;
const int ENB = 11;    // PWM speed for motor B
const int IN3 = 8;
const int IN4 = 9;

// Ultrasonic sensors
const int TRIG_L = 2;
const int ECHO_L = 4;
const int TRIG_C = 12;
const int ECHO_C = A0;
const int TRIG_R = 13;
const int ECHO_R = A1;
const int MAX_DISTANCE = 200;  // cm

NewPing sonarL(TRIG_L, ECHO_L, MAX_DISTANCE);
NewPing sonarC(TRIG_C, ECHO_C, MAX_DISTANCE);
NewPing sonarR(TRIG_R, ECHO_R, MAX_DISTANCE);

// Servos
const int SERVO_L_PIN = 3;
const int SERVO_R_PIN = 10;
Servo servoL;
Servo servoR;

// Servo positions (degrees)
const int SCOOP_UP_POS = 30;
const int SCOOP_DOWN_POS = 130;

// Speeds
const int SPEED_FAST = 200;
const int SPEED_SLOW = 120;

// Obstacle stop threshold
const int STOP_DISTANCE_CM = 15;
unsigned long lastSonarPoll = 0;
const unsigned long SONAR_INTERVAL = 50;  // ms - sub-50ms polling


// ---------------------------------------------------------------------------
// Motor control
// ---------------------------------------------------------------------------

void motorForward(int speed) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
}

void motorStop() {
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
}

void motorTurnLeft() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  analogWrite(ENA, SPEED_SLOW);
  analogWrite(ENB, SPEED_SLOW);
}

void motorTurnRight() {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  analogWrite(ENA, SPEED_SLOW);
  analogWrite(ENB, SPEED_SLOW);
}


// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(9600);

  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);

  servoL.attach(SERVO_L_PIN);
  servoR.attach(SERVO_R_PIN);
  servoL.write(SCOOP_UP_POS);
  servoR.write(180 - SCOOP_UP_POS);  // mirrored

  motorStop();
}


// ---------------------------------------------------------------------------
// Loop
// ---------------------------------------------------------------------------

void loop() {
  // Continuous ultrasonic obstacle check at sub-50ms intervals
  if (millis() - lastSonarPoll > SONAR_INTERVAL) {
    lastSonarPoll = millis();
    int dC = sonarC.ping_cm();
    if (dC > 0 && dC < STOP_DISTANCE_CM) {
      Serial.println("BLOCKED");
    }
  }

  // Read commands from Pi
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "FWD") {
      motorForward(SPEED_FAST);
    } else if (cmd == "FWD_SLOW") {
      motorForward(SPEED_SLOW);
    } else if (cmd == "STOP") {
      motorStop();
    } else if (cmd == "TURN_L") {
      motorTurnLeft();
    } else if (cmd == "TURN_R") {
      motorTurnRight();
    } else if (cmd == "SCOOP_DOWN") {
      servoL.write(SCOOP_DOWN_POS);
      servoR.write(180 - SCOOP_DOWN_POS);
    } else if (cmd == "SCOOP_UP") {
      servoL.write(SCOOP_UP_POS);
      servoR.write(180 - SCOOP_UP_POS);
    }

    Serial.println("OK");
  }
}
