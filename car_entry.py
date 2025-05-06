import cv2
from ultralytics import YOLO
import os
import time
import serial
import serial.tools.list_ports
import csv
from collections import Counter
import pytesseract
import platform

# Configure Tesseract path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Initialize YOLO model
model = YOLO('best.pt')

# Setup directories and files
save_dir = 'plates'
os.makedirs(save_dir, exist_ok=True)
csv_file = 'plates_log.csv'

if not os.path.exists(csv_file):
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Plate Number', 'Payment Status', 'Timestamp'])

def detect_arduino_port():
    """Detect Arduino port automatically"""
    ports = list(serial.tools.list_ports.comports())
    system = platform.system()

    for port in ports:
        if system == "Linux":
            if "ttyUSB" in port.device or "ttyACM" in port.device:
                return port.device
        elif system == "Darwin": 
            if "usbmodem" in port.device or "usbserial" in port.device:
                return port.device
        elif system == "Windows":
            if "COM" in port.device:
                return port.device
    return None

# Initialize Arduino connection
arduino_port = detect_arduino_port()
arduino = None

if arduino_port:
    try:
        arduino = serial.Serial(arduino_port, 9600, timeout=1)
        time.sleep(2)  # Wait for connection to establish
        print(f"[CONNECTED] Arduino on {arduino_port}")
    except serial.SerialException as e:
        print(f"[ERROR] Failed to connect to Arduino: {e}")
else:
    print("[WARNING] Arduino not detected. Running in camera-only mode.")

def read_distance(arduino):
    """Read distance from Arduino with proper error handling"""
    try:
        if arduino and arduino.in_waiting > 0:
            line = arduino.readline().decode('utf-8').strip()
            if line:  # Only try to convert if we got data
                return float(line)
    except (serial.SerialException, ValueError, UnicodeDecodeError) as e:
        print(f"[SERIAL ERROR] {e}")
    return None

# Initialize video capture
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("[ERROR] Could not open video capture")
    exit()

# Plate detection variables
plate_buffer = []
entry_cooldown = 300  # 5 minutes in seconds
last_saved_plate = None
last_entry_time = 0
results = None

print("[SYSTEM] Ready. Press 'q' to exit.")

while True:
    # Read frame from camera
    ret, frame = cap.read()
    if not ret:
        print("[WARNING] Failed to capture frame")
        break
    
    # Read distance from sensor
    distance = read_distance(arduino)
    
    # Only process if we have a valid distance reading
    if distance is not None:
        print(f"[SENSOR] Distance: {distance} cm")
        
        # Check if vehicle is close enough
        if distance <= 50:
            # Run license plate detection
            results = model(frame)
            
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = frame[y1:y2, x1:x2]
                    
                    # Preprocess image for OCR
                    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                    blur = cv2.GaussianBlur(gray, (5, 5), 0)
                    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                    
                    # Perform OCR
                    plate_text = pytesseract.image_to_string(
                        thresh, 
                        config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                    ).strip().replace(" ", "")
                    
                    # Validate plate format (RA1234A pattern)
                    if "RA" in plate_text:
                        start_idx = plate_text.find("RA")
                        plate_candidate = plate_text[start_idx:]
                        
                        if len(plate_candidate) >= 7:
                            plate_candidate = plate_candidate[:7]
                            prefix, digits, suffix = plate_candidate[:3], plate_candidate[3:6], plate_candidate[6]
                            
                            if (prefix.isalpha() and prefix.isupper() and
                                digits.isdigit() and suffix.isalpha() and suffix.isupper()):
                                
                                print(f"[VALID] Plate Detected: {plate_candidate}")
                                plate_buffer.append(plate_candidate)
                                
                                # Save plate image
                                timestamp_str = time.strftime('%Y%m%d_%H%M%S')
                                image_filename = f"{plate_candidate}_{timestamp_str}.jpg"
                                save_path = os.path.join(save_dir, image_filename)
                                cv2.imwrite(save_path, plate_img)
                                print(f"[IMAGE SAVED] {save_path}")
                                
                                # Show processed images
                                cv2.imshow("Plate", plate_img)
                                cv2.imshow("Processed", thresh)
                                
                                # Check if we have enough detections
                                if len(plate_buffer) >= 3:
                                    most_common = Counter(plate_buffer).most_common(1)[0][0]
                                    current_time = time.time()
                                    
                                    # Check cooldown period
                                    if (most_common != last_saved_plate or 
                                        (current_time - last_entry_time) > entry_cooldown):
                                        
                                        # Log to CSV
                                        with open(csv_file, 'a', newline='') as f:
                                            writer = csv.writer(f)
                                            writer.writerow([
                                                most_common, 
                                                0,  # Payment status (0 = unpaid)
                                                time.strftime('%Y-%m-%d %H:%M:%S')
                                            ])
                                        print(f"[SAVED] {most_common} logged to CSV.")
                                        
                                        # Control gate if Arduino is connected
                                        if arduino:
                                            try:
                                                arduino.write(b'1')
                                                print("[GATE] Opening gate (sent '1')")
                                                time.sleep(15)  # Keep gate open for 15 seconds
                                                arduino.write(b'0')
                                                print("[GATE] Closing gate (sent '0')")
                                            except serial.SerialException as e:
                                                print(f"[GATE ERROR] {e}")
                                        
                                        last_saved_plate = most_common
                                        last_entry_time = current_time
                                    else:
                                        print("[SKIPPED] Duplicate within 5 min window.")
                                    
                                    plate_buffer.clear()
    
    # Display the frame
    if distance is not None and distance <= 50 and results is not None:
        annotated_frame = results[0].plot()
    else:
        annotated_frame = frame
    
    cv2.imshow('Webcam Feed', annotated_frame)
    
    # Add small delay and check for quit command
    time.sleep(0.1)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
if arduino:
    arduino.close()
cv2.destroyAllWindows()
print("[SYSTEM] Shutdown complete")