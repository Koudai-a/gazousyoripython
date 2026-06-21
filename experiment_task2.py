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

def clean_jpeg_data(raw_buffer):
    """
    混ざり込んだテキストノイズの除去フィルター。
    Arduino側から送信される画像データから、JPEGマーカー (FF D8 〜 FF D9) を抽出し、
    途中に挟み込まれる "ACK" などのテキストゴミデータを読み飛ばします。
    """
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
            # Arduinoが途中で挟んでくるテキストメッセージを検知してスキップ
            if i < n - 3 and raw_buffer[i:i+3] == b"ACK":
                # 改行('\n' = 0x0A) が来るまで読み飛ばす
                while i < n and raw_buffer[i] != 0x0A:
                    i += 1
                i += 1 # '\n'の分をスキップ
                continue
                
            cleaned_jpeg += bytes([raw_buffer[i]])
            
            # JPEGの終了マーカーに到達したら抽出を完了
            if len(cleaned_jpeg) >= 2 and cleaned_jpeg[-2] == 0xFF and cleaned_jpeg[-1] == 0xD9:
                break
            i += 1
    return cleaned_jpeg, jpeg_started

def capture_single_frame(ser):
    """
    Arduinoに対して撮影コマンドを送り、シリアル通信経由で1フレームの画像を受信して復元します。
    """
    # 以前の受信バッファの残骸をクリアしてデータのズレを防ぐ
    ser.reset_input_buffer()
    
    # 撮影コマンド (0x10) を送信
    ser.write(CMD_CAPTURE)
    
    raw_buffer = b""
    start_time = time.time()
    
    # データを受信するループ
    while True:
        chunk = ser.read(1024)
        if chunk:
            raw_buffer += chunk
            start_time = time.time()
            # JPEGの終了マーカー (FF D9) が含まれていたら受信完了とする
            if b"\xff\xd9" in raw_buffer:
                break
        else:
            # 3秒間データが届かなければタイムアウト
            if time.time() - start_time > 3.0:
                print("エラー: 通信がタイムアウトしました。")
                return None
                
    # ノイズの除去
    cleaned_jpeg, jpeg_started = clean_jpeg_data(raw_buffer)
    
    if len(cleaned_jpeg) > 0 and jpeg_started:
        # numpy配列経由でOpenCV画像にデコード
        data_array = np.frombuffer(cleaned_jpeg, dtype=np.uint8)
        img = cv2.imdecode(data_array, cv2.IMREAD_COLOR)
        return img
    return None

def run_task1(ser):
    """
    【課題1】
    静止画をキャプチャし、ピクチャフォルダへ保存して画面に表示します。
    """
    print("\n--- [課題1] 静止画キャプチャを実行します ---")
    img = capture_single_frame(ser)
    
    if img is not None:
        print("【大成功】画像の復元に成功しました！")
        
        # ピクチャフォルダにタイムスタンプ付きで保存
        pictures_dir = Path.home() / "Pictures"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"arducam_{timestamp}.jpg"
        save_path = pictures_dir / filename
        cv2.imwrite(str(save_path), img)
        print(f"📂 画像を保存しました: {save_path}")

        # ウィンドウに画像を表示
        cv2.imshow("ArduCAM Captured Image (Task 1)", img)
        print("※画像ウィンドウを選択した状態で、何かキーを押すと終了します。")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        print("エラー: 静止画の取得に失敗しました。")

def run_task2(ser):
    """
    【課題2】
    動画（連続した静止画）を取得して表示し、平均フレームレートを算出します。
    
    【追加方法の指示 (仕様解説)】
    動画の取得方法には、以下の2通りが考えられます：
    A. 連続して実行する方法 (連続キャプチャループ):
       PC側から連続して撮影コマンドを送信し続け、受信した画像をパラパラ漫画のように
       連続描画して動画として見せる方法。今回の実装ではこの方法を採用しています。
    B. ボタンで切り替える方法:
       画面上のボタン押下などのイベントトリガーをきっかけに撮影を行う方法。
    """
    print("\n--- [課題2] 動画表示を開始します ---")
    print("※画像ウィンドウを選択した状態で、何かキーを押すと終了します。")
    
    frame_count = 0
    start_time = time.time()
    
    # ポートの安定化のために少しウェイトを入れる
    time.sleep(0.5)
    
    try:
        while True:
            frame_start = time.time()
            
            # 連続して次のフレームをキャプチャ
            img = capture_single_frame(ser)
            
            if img is not None:
                frame_count += 1
                
                # 今回のフレームにかかった時間から現在のFPSを簡易計算
                frame_time = time.time() - frame_start
                current_fps = 1.0 / frame_time if frame_time > 0 else 0.0
                
                # 画像の左上に現在のフレームレートを描画 (見やすさのため)
                cv2.putText(img, f"FPS: {current_fps:.2f}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                
                # ウィンドウに動画として描画
                cv2.imshow("ArduCAM Video Stream (Task 2)", img)
            else:
                print("警告: フレームのデコードに失敗しました。")
            
            # 何かキーが押されたらループを抜ける (待機時間 1ms)
            # cv2.waitKey(1) はキーが押されていない間は -1 を返すため、
            # 戻り値が -1 以外の時に終了判定とします
            key = cv2.waitKey(1)
            if key != -1:
                print(f"\nキー入力を検知しました (Keycode: {key})。動画取得を終了します。")
                break
                
    finally:
        # ループを抜けたら必ずウィンドウを破棄
        cv2.destroyAllWindows()
        
        # 平均フレームレートの計算と出力
        end_time = time.time()
        total_time = end_time - start_time
        
        if total_time > 0 and frame_count > 0:
            avg_fps = frame_count / total_time
            print("\n========================================")
            print("【実験結果 (課題2)】")
            print(f" 総取得フレーム数  : {frame_count} frames")
            print(f" 総実行時間        : {total_time:.2f} seconds")
            print(f" 平均フレームレート : {avg_fps:.2f} FPS")
            print("========================================\n")
        else:
            print("有効なフレームが取得されなかったため、平均フレームレートを計算できませんでした。")

def main():
    print(f"[{SERIAL_PORT}] ポートを開いています...")
    try:
        # 【重要】シリアルポートはここで1回だけオープンし、動画ループ中はずっと開いたままにします。
        # フレームごとにポートの開け閉めを行うと、Arduinoのリセット信号 (DTR) が発生し、
        # 接続待ちウェイト (2.5秒) が毎回発生してしまい、動画として機能しなくなるためです。
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5.0)
        ser.set_buffer_size(rx_size=1024 * 1024, tx_size=65536)
    except Exception as e:
        print(f"エラー: ポートを開けませんでした。\n{e}")
        return

    # Arduinoの起動接続待ちウェイト
    time.sleep(2.5)
    ser.reset_input_buffer()

    try:
        print("\n実行する課題のモードを選択してください:")
        print("1: 【課題1】 静止画キャプチャ ＆ 保存")
        print("2: 【課題2】 動画表示 ＆ 平均フレームレート出力")
        choice = input("選択してください (1 または 2): ").strip()
        
        if choice == "1":
            run_task1(ser)
        elif choice == "2":
            run_task2(ser)
        else:
            print("無効な入力です。プログラムを終了します。")
            
    finally:
        # 最後に必ずポートをクローズ
        print("シリアルポートを閉じています...")
        ser.close()
        print("終了しました。")

if __name__ == "__main__":
    main()
