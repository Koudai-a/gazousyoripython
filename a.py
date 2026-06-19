import serial
import time
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path

# ===================================================
# 設定パラメータ
# ===================================================
SERIAL_PORT = "COM6"       
BAUD_RATE = 921600         
CMD_CAPTURE = b'\x10'      

def main():
    print(f"[{SERIAL_PORT}] ポートを開いています...")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5.0)
        ser.set_buffer_size(rx_size=1024 * 1024, tx_size=65536)
    except Exception as e:
        print(f"エラー: ポートを開けませんでした。\n{e}")
        return

    time.sleep(2.5)
    ser.reset_input_buffer()

    print("Arduinoへ撮影コマンド (0x10) を送信します...")
    ser.write(CMD_CAPTURE)
    
    print("データ受信中...（ノイズを除去しながらJPEGを抽出します）")
    
    raw_buffer = b""
    start_time = time.time()
    
    while True:
        chunk = ser.read(1024)
        if chunk:
            raw_buffer += chunk
            start_time = time.time()
            if b"\xff\xd9" in raw_buffer:
                print("→ 受信完了。データ整形中...")
                break
        else:
            if time.time() - start_time > 3.0:
                print("エラー: 通信がタイムアウトしました。")
                break

    ser.close()

    # --- 🛠️ 混ざり込んだテキストノイズの除去フィルター ---
    cleaned_jpeg = b""
    jpeg_started = False
    i = 0
    n = len(raw_buffer)

    while i < n:
        if not jpeg_started:
            if i < n - 1 and raw_buffer[i] == 0xFF and raw_buffer[i+1] == 0xD8:
                jpeg_started = True
                cleaned_jpeg += b"\xff\xd8"
                i += 2
                continue
            i += 1
        else:
            if i < n - 3 and raw_buffer[i:i+3] == b"ACK":
                while i < n and raw_buffer[i] != 0x0A:
                    i += 1
                i += 1 
                continue
                
            cleaned_jpeg += bytes([raw_buffer[i]])
            
            if len(cleaned_jpeg) >= 2 and cleaned_jpeg[-2] == 0xFF and cleaned_jpeg[-1] == 0xD9:
                break
            i += 1

    # --- OpenCVで画像に復元して表示 ＆ 保存 ---
    if len(cleaned_jpeg) > 0 and jpeg_started:
        data_array = np.frombuffer(cleaned_jpeg, dtype=np.uint8)
        img = cv2.imdecode(data_array, cv2.IMREAD_COLOR)

        if img is not None:
            print("【大成功】画像の復元に成功しました！")
            
            # --- 💾 ピクチャフォルダーへの保存処理 ---
            pictures_dir = Path.home() / "Pictures"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"arducam_{timestamp}.jpg"
            save_path = pictures_dir / filename
            
            cv2.imwrite(str(save_path), img)
            print(f"📂 画像をピクチャに保存しました:\n   {save_path}")
            # --------------------------------------------------

            cv2.imshow("ArduCAM Captured Image", img)
            print("※画像ウィンドウを選択した状態で、何かキーを押すと終了します。")
            cv2.waitKey(0)  
            cv2.destroyAllWindows()
        else:
            print("エラー: 画像のデコードに失敗しました。")
    else:
        print("エラー: 有効な画像データを受信できませんでした。")

if __name__ == "__main__":
    main()