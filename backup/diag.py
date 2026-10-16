import cv2
from cvzone.HandTrackingModule import HandDetector

cap = cv2.VideoCapture(0)
detector = HandDetector(detectionCon=0.8, maxHands=2)

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.flip(frame, 1)
    hands, frame = detector.findHands(frame, draw=True, flipType=False)
    for i, m in enumerate(hands):
        dedos = detector.fingersUp(m)
        print(list(m.keys()), repr(m.get("type")), dedos)
        cv2.putText(frame, f"{m.get('type')} {dedos}", (20, 40 + 30 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow("diag", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()