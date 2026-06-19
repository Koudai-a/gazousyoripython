import serial
import time
import cv2
import numpy as np

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
    
    # データをすべて受け取るまで回す
    while True:
        chunk = ser.read(1024)
        if chunk:
            raw_buffer += chunk
            start_time = time.time()
            
            # JPEGの終わり(FF D9)がバッファのどこかに含まれたら受信完了とする
            if b"\xff\xd9" in raw_buffer:
                print("→ 受信完了。これからデータ内のゴミテキストを掃除します...")
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
        # JPEGの開始(FF D8)を見つけたら、そこから抽出スタート
        if not jpeg_started:
            if i < n - 1 and raw_buffer[i] == 0xFF and raw_buffer[i+1] == 0xD8:
                jpeg_started = True
                cleaned_jpeg += b"\xff\xd8"
                i += 2
                continue
            i += 1
        else:
            # Arduinoが途中で挟んでくる「ACK」などのテキストメッセージをスキップする
            # ※ 'A'(0x41), 'C'(0x43), 'K'(0x4B), '\r'(0x0D), '\n'(0x0A) などの文字列領域を検知
            if i < n - 3 and raw_buffer[i:i+3] == b"ACK":
                # 改行('\n')が来るまで読み飛ばす
                while i < n and raw_buffer[i] != 0x0A:
                    i += 1
                i += 1 # '\n'の分をスキップ
                print("→ 途中に混入したテキストメッセージ(ACK CMD...)を検知し、除去しました。")
                continue
                
            # 通常の画像データとして追加
            cleaned_jpeg += bytes([raw_buffer[i]])
            
            # JPEGの終了(FF D9)に到達したら終了
            if len(cleaned_jpeg) >= 2 and cleaned_jpeg[-2] == 0xFF and cleaned_jpeg[-1] == 0xD9:
                break
            i += 1

    print(f"元の受信サイズ: {len(raw_buffer)} バイト ➔ 掃除後のJPEGサイズ: {len(cleaned_jpeg)} バイト")

    # --- OpenCVで画像に復元して表示 ---
    if len(cleaned_jpeg) > 0 and jpeg_started:
        data_array = np.frombuffer(cleaned_jpeg, dtype=np.uint8)
        img = cv2.imdecode(data_array, cv2.IMREAD_COLOR)

        if img is not None:
            print("【大成功】ゴミの除去に成功し、画像が復元されました！")
            cv2.imshow("ArduCAM Captured Image", img)
            print("※画像ウィンドウを選択した状態で、何かキーを押すと終了します。")
            cv2.waitKey(0)  
            cv2.destroyAllWindows()
        else:
            print("エラー: 画像のデコードに失敗しました。まだゴミが残っているか、データが欠損しています。")
    else:
        print("エラー: 有効な画像マーカーが見つかりませんでした。")

if __name__ == "__main__":
    main()