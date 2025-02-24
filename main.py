import telebot
import sqlite3
from fuzzywuzzy import fuzz, process

# 📌 Telegram bot token'ı "token.txt" dosyasından alınıyor
with open("token.txt", "r") as file:
    TOKEN = file.read().strip()

bot = telebot.TeleBot(TOKEN)

# 📌 SQL database yolu
DATABASE_PATH = "bot_database.db"


# 📌 Log fonksiyonu (Terminalde süreci izleyelim)
def log(message):
    print(f"[LOG] {message}")


# 📌 Kullanıcı girişlerini kaydetme fonksiyonu
def log_user_input(user_id, input_text):
    print(f"[USER INPUT] UserID: {user_id}, Input: {input_text}")


# 📌 Bot cevaplarını kaydetme fonksiyonu
def log_bot_response(user_id, response_text):
    print(f"[BOT RESPONSE] UserID: {user_id}, Response: {response_text}")


# 📌 Veritabanı bağlantısı oluştur
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# 📌 Veritabanı tablolarını oluşturma
def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ilcebilgileri (
            PlakaKodu TEXT,
            City TEXT,
            District TEXT,
            Phone TEXT,
            IPPhone TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_data (
            UserID INTEGER PRIMARY KEY,
            Username TEXT,
            City TEXT,
            District TEXT,
            Role TEXT,
            ContactPermission TEXT
        )
    ''')

    conn.commit()
    conn.close()


# 📌 Kullanıcı kayıt kontrolü
def get_user_data(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM user_data WHERE UserID = ?", (user_id,))
    user_data = cursor.fetchone()

    conn.close()
    return user_data


# 📌 Kullanıcı kaydetme / Güncelleme
def save_user_data(user_id, username, city, district, permission):
    # user_id'yi tamsayıya dönüştür
    user_id = int(user_id)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO user_data (UserID, Username, City, District, ContactPermission)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(UserID) DO UPDATE SET
        Username=excluded.Username,
        City=excluded.City,
        District=excluded.District,
        ContactPermission=excluded.ContactPermission
    ''', (user_id, username, city, district, permission))

    conn.commit()
    conn.close()

    log(f"Kullanıcı kaydedildi/güncellendi: {user_id} - {username} ({city}, {district})")


# 📌 İlgili vakıf çalışanlarını bul
def get_relevant_staff(city, district):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT UserID, Username FROM user_data
        WHERE lower(City) = ? AND lower(District) = ? AND lower(ContactPermission) = 'evet'
    ''', (city.lower(), district.lower()))
    staff = cursor.fetchall()

    conn.close()
    return [dict(row) for row in staff]


# 📌 Özel mesaja geçmeyi dene
def try_send_private_message(user_id, text):
    try:
        bot.send_message(user_id, text)
        log_bot_response(user_id, text)
        return True
    except:
        return False


# 📌 Bot mesaj gönderme fonksiyonu
def send_message(user_id, text, reply_markup=None):
    bot.send_message(user_id, text, reply_markup=reply_markup)
    log_bot_response(user_id, text)


# 📌 /tani komutu
@bot.message_handler(commands=["tani"])
def handle_tani(message):
    user_id = message.from_user.id
    username = message.from_user.username

    # Özel mesaj kontrolü
    if not try_send_private_message(user_id, "Merhaba! Kayıt durumunuzu kontrol ediyorum..."):
        bot.reply_to(message, f"Lütfen özelden yazın: [Bot Linki](t.me/{bot.get_me().username})", parse_mode="Markdown")
        return

    log(f"/tani komutu çalıştı - Kullanıcı ID: {user_id}")

    # Kullanıcı zaten kayıtlı mı?
    user_data = get_user_data(user_id)
    if user_data is not None:
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Evet", "Hayır")
        msg = bot.send_message(user_id, "Zaten kayıtlısınız! Bilgilerinizi güncellemek ister misiniz?",
                               reply_markup=markup)
        bot.register_next_step_handler(msg, update_user_data)
        return

    msg = bot.send_message(user_id, "Lütfen plaka kodunuzu girin:")
    log_bot_response(user_id, "Lütfen plaka kodunuzu girin:")
    bot.register_next_step_handler(msg, ask_district)


# 📌 Kullanıcı bilgilerinin güncellenmesi
def update_user_data(message):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    if message.text.lower() == "evet":
        msg = bot.send_message(message.chat.id, "Lütfen plaka kodunuzu girin:")
        log_bot_response(message.chat.id, "Lütfen plaka kodunuzu girin:")
        bot.register_next_step_handler(msg, ask_district)
    else:
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("/talep")  # Kullanıcıya buton olarak /talep sunuluyor
        send_message(message.chat.id, "Bilgileriniz değiştirilmeyecek. Dilerseniz transfer /talep edebilirsiniz.",
                     reply_markup=markup)


# 📌 İlçeyi sor
def ask_district(message):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    plaka_kodu = message.text.strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ilcebilgileri WHERE PlakaKodu = ?", (plaka_kodu,))
    districts = cursor.fetchall()
    conn.close()

    if not districts:
        msg = bot.send_message(user_id, "Geçersiz plaka kodu! Tekrar girin:")
        log_bot_response(user_id, "Geçersiz plaka kodu! Tekrar girin:")
        bot.register_next_step_handler(msg, ask_district)
        return

    # İlçeleri listele ve butonlarla sun
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for district in districts:
        markup.add(district["District"])

    msg = bot.send_message(user_id, "Lütfen ilçenizi seçin:", reply_markup=markup)
    log_bot_response(user_id, "Lütfen ilçenizi seçin:")
    bot.register_next_step_handler(msg, ask_contact_permission, plaka_kodu)


# 📌 Kullanıcıdan iletişim izni iste
def ask_contact_permission(message, plaka_kodu):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    selected_district = message.text.strip()

    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Evet", "Hayır")

    msg = bot.send_message(user_id, "İletişime geçilmesine izin veriyor musunuz?", reply_markup=markup)
    log_bot_response(user_id, "İletişime geçilmesine izin veriyor musunuz?")
    bot.register_next_step_handler(msg, finalize_registration, plaka_kodu, selected_district)


# 📌 Kaydı tamamla
def finalize_registration(message, plaka_kodu, district):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    username = message.from_user.username
    permission = message.text.strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT City FROM ilcebilgileri WHERE District = ?", (district,))
    city_row = cursor.fetchone()
    conn.close()

    if city_row:
        city = city_row["City"]
        save_user_data(user_id, username, city, district, permission)
        send_message(user_id, "Kayıt tamamlandı! Artık /talep komutunu kullanabilirsiniz. ✅")
    else:
        send_message(user_id, "İlçe bilgileri bulunamadı. Lütfen tekrar deneyin.")


# 📌 /talep komutu
@bot.message_handler(commands=["talep"])
def handle_talep(message):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)

    # Özel mesaj kontrolü
    if not try_send_private_message(user_id, "Talep işlemini başlatıyorum..."):
        bot.reply_to(message, f"Lütfen özelden yazın: [Bot Linki](t.me/{bot.get_me().username})", parse_mode="Markdown")
        return

    if get_user_data(user_id) is None:
        send_message(user_id, "Önce kayıt olmalısınız. Lütfen /tani komutunu kullanın.")
        return

    msg = bot.send_message(user_id, "Lütfen talep tipini seçin:", reply_markup=get_talep_tipi_markup())
    log_bot_response(user_id, "Lütfen talep tipini seçin:")
    bot.register_next_step_handler(msg, ask_district_for_talep)


def get_talep_tipi_markup():
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Hane", "Kişi")
    return markup


# 📌 Talep için ilçe adı sor
def ask_district_for_talep(message):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    talep_tipi = message.text.strip().lower()

    msg = bot.send_message(user_id, "Lütfen ilçeyi girin:", reply_markup=telebot.types.ReplyKeyboardRemove())
    log_bot_response(user_id, "Lütfen ilçeyi girin:")
    bot.register_next_step_handler(msg, process_district, talep_tipi)


# 📌 İlçe adı işleme
def process_district(message, talep_tipi):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    district_input = message.text.strip().lower()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT District FROM ilcebilgileri")
    districts = [row["District"].lower() for row in cursor.fetchall()]
    conn.close()

    # İlçe adı %100 doğruysa doğrudan işle
    if district_input in districts:
        handle_city_selection(message, district_input, talep_tipi, None)
        return

    # FuzzyWuzzy ile en olası ilçeleri bul
    matches = process.extract(district_input, districts, limit=4)
    high_confidence_matches = [match for match in matches if match[1] > 80]

    if not high_confidence_matches:
        msg = bot.send_message(user_id, "Geçersiz ilçe girdiniz! Lütfen doğru ilçeyi yazın.",
                               reply_markup=telebot.types.ReplyKeyboardRemove())
        log_bot_response(user_id, "Geçersiz ilçe girdiniz! Lütfen doğru ilçeyi yazın.")
        bot.register_next_step_handler(msg, process_district, talep_tipi)
        return

    # İlçeleri listele ve butonlarla sun
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for match in high_confidence_matches:
        markup.add(match[0].title())
    markup.add("Değiştir")

    msg = bot.send_message(user_id, "Lütfen ilçenizi seçin veya 'Değiştir' butonuna basın:", reply_markup=markup)
    log_bot_response(user_id, "Lütfen ilçenizi seçin veya 'Değiştir' butonuna basın:")
    bot.register_next_step_handler(msg, validate_district_selection, talep_tipi, district_input)


# 📌 İlçe seçim doğrulama
def validate_district_selection(message, talep_tipi, original_input):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    selected_district = message.text.strip().lower()

    if selected_district == "değiştir":
        msg = bot.send_message(user_id, "Lütfen ilçeyi tekrar girin:", reply_markup=telebot.types.ReplyKeyboardRemove())
        log_bot_response(user_id, "Lütfen ilçeyi tekrar girin:")
        bot.register_next_step_handler(msg, process_district, talep_tipi)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ilcebilgileri WHERE lower(District) = ?", (selected_district,))
    district_data = cursor.fetchone()
    conn.close()

    if not district_data:
        msg = bot.send_message(user_id, "Geçersiz ilçe! Tekrar deneyin:",
                               reply_markup=telebot.types.ReplyKeyboardRemove())
        log_bot_response(user_id, "Geçersiz ilçe! Tekrar deneyin:")
        bot.register_next_step_handler(msg, process_district, talep_tipi)
        return

    handle_city_selection(message, selected_district, talep_tipi, district_data["City"])


def handle_city_selection(message, selected_district, talep_tipi, city):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)

    if city is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT City FROM ilcebilgileri WHERE lower(District) = ?", (selected_district,))
        city_row = cursor.fetchone()
        conn.close()
        if not city_row:
            msg = bot.send_message(user_id, "İlçe ve şehir bilgileri uyumsuz. Lütfen tekrar deneyin.",
                                   reply_markup=telebot.types.ReplyKeyboardRemove())
            log_bot_response(user_id, "İlçe ve şehir bilgileri uyumsuz. Lütfen tekrar deneyin.")
            bot.register_next_step_handler(msg, process_district, talep_tipi)
            return
        city = city_row["City"]

    finalize_talep_with_city(user_id, selected_district, talep_tipi, city)


def finalize_talep_with_city(user_id, district, talep_tipi, city):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ilcebilgileri WHERE lower(District) = ? AND lower(City) = ?", (district, city))
    district_data = cursor.fetchone()

    if not district_data:
        send_message(user_id, "İlçe ve şehir bilgileri uyumsuz. Lütfen tekrar deneyin.",
                     reply_markup=telebot.types.ReplyKeyboardRemove())
        return

    user_data = get_user_data(user_id)
    if user_data is None:
        send_message(user_id, "Kullanıcı verileri bulunamadı.", reply_markup=telebot.types.ReplyKeyboardRemove())
        return

    user_city = user_data["City"]
    user_district = user_data["District"]

    phone = district_data["Phone"]
    ip_phone = district_data["IPPhone"]

    relevant_staff = get_relevant_staff(city, district)
    if relevant_staff:
        staff_list = "\n".join([
                                   f'    <a href="tg://user?id={staff["UserID"]}" class="mention">@{staff["Username"] if staff["Username"] else "Kullanıcı"}</a>'
                                   for staff in relevant_staff])
    else:
        staff_list = "    Vakıf çalışanı bulunamadı"

    bot.send_message(-4639327269,
                     f"Transfer Talebi Var! 📢\n\n"
                     f"    👤 Talep Eden Vakıf: {user_city} - {user_district}\n"
                     f"    🏠 Talep Türü: {talep_tipi}\n"
                     f"    📍 Talep Edilen Vakıf: {city} - {district}\n\n"
                     f"    ☎️ İletişim Bilgileri:\n"
                     f"    📞 Telefon: {phone}\n"
                     f"    📱 IP Telefon: {ip_phone}\n\n"
                     f"    📌 İlgili Vakıf Çalışanları:\n"
                     f"{staff_list}",
                     parse_mode="HTML")
    send_message(user_id, "Talebiniz iletildi! ✅", reply_markup=telebot.types.ReplyKeyboardRemove())


# 📌 Bot başlatma
if __name__ == "__main__":
    create_tables()
    bot.polling()
