#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 9
#define SS_PIN 10

MFRC522 mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

const int PLATE_BLOCK = 2;
const int BALANCE_BLOCK = 4;

int amountToAdd = 0;
bool waitingForInput = false;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();

  for (byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }

  Serial.println("Parking Payment System");
  Serial.println("1. Scan your RFID card to view plate number and balance.");
  Serial.println("2. Then enter amount via Serial Monitor to add money.");
}

void loop() {
  if (Serial.available() && waitingForInput) {
    String input = Serial.readStringUntil('\n');
    amountToAdd = input.toInt();

    if (amountToAdd > 0) {
      processPayment();
      waitingForInput = false;
      mfrc522.PICC_HaltA();
      mfrc522.PCD_StopCrypto1();
      Serial.println("\nReady for a new transaction. Scan a card...");
    } else {
      Serial.println("Invalid amount! Please enter a positive integer.");
    }
  }

  if (!waitingForInput && mfrc522.PICC_IsNewCardPresent() && mfrc522.PICC_ReadCardSerial()) {
    displayCardInfo();
    waitingForInput = true;
  }
}

void displayCardInfo() {
  Serial.println("\n--- Card Detected ---");

  byte status;
  byte buffer[18];
  byte size = sizeof(buffer);

  // Read plate number
  status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, PLATE_BLOCK, &key, &(mfrc522.uid));
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Authentication failed for plate number reading");
    return;
  }

  status = mfrc522.MIFARE_Read(PLATE_BLOCK, buffer, &size);
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Reading plate number failed");
    return;
  }

  char plateNumber[8]; // 7 chars + null terminator
  memcpy(plateNumber, buffer, 7);
  plateNumber[7] = '\0'; // Ensure null-termination

  Serial.print("Plate Number: ");
  Serial.println(plateNumber);

  // Read balance
  status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, BALANCE_BLOCK, &key, &(mfrc522.uid));
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Authentication failed for balance reading");
    return;
  }

  status = mfrc522.MIFARE_Read(BALANCE_BLOCK, buffer, &size);
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Reading balance failed");
    return;
  }

  float currentBalance;
  memcpy(&currentBalance, buffer, sizeof(float));

  Serial.print("Current Balance: RWF ");
  Serial.println(currentBalance, 2);
  Serial.print("Enter amount to add and press Enter: ");
}

void processPayment() {
  Serial.println("\n--- Processing Payment ---");

  byte status;
  byte buffer[18];
  byte size = sizeof(buffer);

  // Authenticate and read current balance
  status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, BALANCE_BLOCK, &key, &(mfrc522.uid));
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Authentication failed for balance reading during payment");
    return;
  }

  status = mfrc522.MIFARE_Read(BALANCE_BLOCK, buffer, &size);
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Reading balance failed during payment");
    return;
  }

  float currentBalance;
  memcpy(&currentBalance, buffer, sizeof(float));
  float newBalance = currentBalance + amountToAdd;

  byte writeBuffer[16];
  memset(writeBuffer, 0, sizeof(writeBuffer));
  memcpy(writeBuffer, &newBalance, sizeof(float));

  // Authenticate again before writing
  status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, BALANCE_BLOCK, &key, &(mfrc522.uid));
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Authentication failed for balance writing");
    return;
  }

  status = mfrc522.MIFARE_Write(BALANCE_BLOCK, writeBuffer, 16);
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Writing new balance failed");
    return;
  }

  delay(100);

  // Verify the write
  status = mfrc522.MIFARE_Read(BALANCE_BLOCK, buffer, &size);
  if (status != MFRC522::STATUS_OK) {
    Serial.println("Reading verification failed");
    return;
  }

  float verifiedBalance;
  memcpy(&verifiedBalance, buffer, sizeof(float));

  Serial.print("Added RWF ");
  Serial.print(amountToAdd);
  Serial.print(". New Balance: RWF ");
  Serial.println(verifiedBalance, 2);

  if (verifiedBalance != newBalance) {
    Serial.println("Warning: Balance verification failed!");
  }

  // Show updated card details again
  displayCardInfo();
}

