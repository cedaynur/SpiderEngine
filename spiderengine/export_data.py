import sqlite3
import os

def export_to_pdata():
    # Klasörü oluştur
    os.makedirs("data/storage", exist_ok=True)
    
    # Veritabanına bağlan (Dosya yolunun doğru olduğundan emin ol)
    conn = sqlite3.connect("data/crawler.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Tüm dökümanları çek
        cursor.execute("SELECT url, origin_url, depth, content FROM documents")
        rows = cursor.fetchall()

        with open("data/storage/p.data", "w", encoding="utf-8") as f:
            for row in rows:
                url = row["url"]
                origin = row["origin_url"]
                depth = row["depth"]
                content = row["content"].lower()
                
                # İçerikteki kelimeleri ayır ve her kelime için bir satır yaz
                words = content.split()
                # Kelime frekanslarını hesapla
                word_counts = {}
                for w in words:
                    # Sadece harf ve rakam olan temiz kelimeleri al
                    clean_w = "".join(filter(str.isalnum, w))
                    if len(clean_w) > 2: # Çok kısa kelimeleri atla
                        word_counts[clean_w] = word_counts.get(clean_w, 0) + 1

                for word, freq in word_counts.items():
                    # Format: word url origin depth frequency
                    line = f"{word} {url} {origin} {depth} {freq}\n"
                    f.write(line)
        
        print("[+] data/storage/p.data başarıyla oluşturuldu!")
        
    except Exception as e:
        print(f"[-] Hata oluştu: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export_to_pdata()