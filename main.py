import telebot
import pandas as pd
import os
from fuzzywuzzy import fuzz, process

# 📌 Telegram bot token'ı "token.txt" dosyasından alınıyor
with open("token.txt", "r") as file:
    TOKEN = file.read().strip()

bot = telebot.TeleBot(TOKEN)

# 📌 Excel dosya yolları
ILCE_BILGILERI_PATH = "ilcebilgileri.xlsx"
USER_DATA_PATH = "user_data.xlsx"


# 📌 Log fonksiyonu (Terminalde süreci izleyelim)
def log(message):
    print(f"[LOG] {message}")


# 📌 User input log fonksiyonu
def log_user_input(user_id, input_text):
    print(f"[USER INPUT] UserID: {user_id}, Input: {input_text}")


# 📌 Excel'den veri yükleme
def load_ilce_data():
    try:
        df = pd.read_excel(ILCE_BILGILERI_PATH, dtype={"PlakaKodu": str})
        log("İlçe bilgileri yüklendi.")
        return df
    except Exception as e:
        log(f"Hata: İlçe bilgileri yüklenemedi. {str(e)}")
        return None


# 📌 Kullanıcı kayıt kontrolü
def get_user_data(user_id):
    if os.path.exists(USER_DATA_PATH):
        df = pd.read_excel(USER_DATA_PATH)
        user_row = df[df["UserID"] == user_id]
        if not user_row.empty:
            return user_row.iloc[0]
    return None


# 📌 İlgili vakıf çalışanlarını bul
def get_relevant_staff(city, district):
    if os.path.exists(USER_DATA_PATH):
        df = pd.read_excel(USER_DATA_PATH)
        staff = df[(df["City"].str.lower() == city.lower()) &
                   (df["District"].str.lower() == district.lower()) &
                   (df["ContactPermission"].str.lower() == "evet")]
        if not staff.empty:
            return staff[["UserID", "Username"]].to_dict('records')
    return []


# 📌 Kullanıcı kaydetme / Güncelleme
def save_user_data(user_id, username, city, district, permission):
    data = {"UserID": [user_id], "Username": [username], "City": [city], "District": [district],
            "ContactPermission": [permission]}

    if os.path.exists(USER_DATA_PATH):
        df = pd.read_excel(USER_DATA_PATH)
        df = df[df["UserID"] != user_id]  # Eski kaydı sil
        df = pd.concat([df, pd.DataFrame(data)], ignore_index=True)
    else:
        df = pd.DataFrame(data)

    df.to_excel(USER_DATA_PATH, index=False)
    log(f"Kullanıcı kaydedildi/güncellendi: {user_id} - {username} ({city}, {district})")


# 📌 Özel mesaja geçmeyi dene
def try_send_private_message(user_id, text):
    try:
        bot.send_message(user_id, text)
        return True
    except:
        return False


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
    bot.register_next_step_handler(msg, ask_district)
    log_user_input(user_id, message.text)


# 📌 Kullanıcı bilgilerinin güncellenmesi
def update_user_data(message):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    if message.text.lower() == "evet":
        bot.send_message(message.chat.id, "Lütfen plaka kodunuzu girin:")
        bot.register_next_step_handler(message, ask_district)
    else:
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("/talep")  # Kullanıcıya buton olarak /talep sunuluyor
        bot.send_message(message.chat.id, "Bilgileriniz değiştirilmeyecek. Dilerseniz transfer /talep edebilirsiniz.",
                         reply_markup=markup)


# 📌 İlçeyi sor
def ask_district(message):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    plaka_kodu = message.text.strip()
    df = load_ilce_data()

    if df is None or plaka_kodu not in df["PlakaKodu"].values:
        msg = bot.send_message(user_id, "Geçersiz plaka kodu! Tekrar girin:")
        bot.register_next_step_handler(msg, ask_district)
        return

    # İlçeleri listele ve butonlarla sun
    available_districts = df[df["PlakaKodu"] == plaka_kodu]["District"].unique()
    if len(available_districts) == 0:
        bot.send_message(user_id, "İlgili plaka kodu için ilçe bulunamadı.")
        return

    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for district in available_districts:
        markup.add(district)

    msg = bot.send_message(user_id, "Lütfen ilçenizi seçin:", reply_markup=markup)
    bot.register_next_step_handler(msg, ask_contact_permission, plaka_kodu)


# 📌 Kullanıcıdan iletişim izni iste
def ask_contact_permission(message, plaka_kodu):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    selected_district = message.text.strip()

    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Evet", "Hayır")

    msg = bot.send_message(user_id, "İletişime geçilmesine izin veriyor musunuz?", reply_markup=markup)
    bot.register_next_step_handler(msg, finalize_registration, plaka_kodu, selected_district)


# 📌 Kaydı tamamla
def finalize_registration(message, plaka_kodu, district):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    username = message.from_user.username
    permission = message.text.strip()

    df = load_ilce_data()
    if df is None:
        bot.send_message(user_id, "İlçe bilgileri yüklenemedi.")
        return

    city = df[df["District"].str.lower() == district.lower()]["City"].values[0]

    save_user_data(user_id, username, city, district, permission)
    bot.send_message(user_id, "Kayıt tamamlandı! Artık /talep komutunu kullanabilirsiniz. ✅")


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
        bot.send_message(user_id, "Önce kayıt olmalısınız. Lütfen /tani komutunu kullanın.")
        return

    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Hane", "Kişi")
    msg = bot.send_message(user_id, "Talep türünü seçin:", reply_markup=markup)
    bot.register_next_step_handler(msg, validate_talep_type)


# Yeni fonksiyon
def validate_talep_type(message):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    talep_tipi = message.text.strip()

    if talep_tipi.lower() not in ["hane", "kişi"]:
        msg = bot.send_message(user_id, "Geçersiz seçim! Lütfen 'Hane' veya 'Kişi' seçeneklerinden birini seçin:")
        bot.register_next_step_handler(msg, validate_talep_type)
        return

    msg = bot.send_message(user_id, "Lütfen ilçeyi girin:")
    bot.register_next_step_handler(msg, process_district, talep_tipi)


# 📌 İlçe adı işleme
def process_district(message, talep_tipi):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    district = message.text.strip().lower()

    df_ilce = load_ilce_data()
    if df_ilce is None:
        bot.send_message(user_id, "İlçe bilgileri yüklenemedi.")
        return

    df_ilce["District"] = df_ilce["District"].astype(str).str.lower()  # Ensure all values in the District column are strings and lowercase
    df_ilce["City"] = df_ilce["City"].astype(str).str.lower()  # Ensure all values in the City column are strings and lowercase

    if district not in df_ilce["District"].tolist():
        # Suggest possible districts
        possible_districts = process.extractBests(district, df_ilce["District"].tolist(), scorer=fuzz.partial_ratio, score_cutoff=75)
        if possible_districts:
            suggestions = [dist[0] for dist in possible_districts]
            suggestions.append("Değiştir")
            markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for suggestion in suggestions:
                markup.add(suggestion)
            msg = bot.send_message(user_id, "Hatalı ilçe girdiniz! Şunu mu demek istediniz?", reply_markup=markup)
            bot.register_next_step_handler(msg, handle_corrected_district, talep_tipi)
            return
        else:
            bot.send_message(user_id, "Hatalı ilçe girdiniz! Lütfen doğru ilçeyi yazın.")
            return

    # Check if the district is "merkez" or if the district name is shared by multiple cities
    if district == "merkez" or df_ilce[df_ilce["District"] == district].shape[0] > 1:
        if district == "merkez":
            msg = bot.send_message(user_id, "Lütfen plaka kodunuzu yazın:")
            bot.register_next_step_handler(msg, handle_plaka_kodu, talep_tipi, district)
        else:
            # Multiple cities have the same district name
            possible_cities = df_ilce[df_ilce["District"] == district]["City"].unique()
            markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for city in possible_cities:
                markup.add(city.title())
            msg = bot.send_message(user_id, "Lütfen il seçin:", reply_markup=markup)
            bot.register_next_step_handler(msg, handle_city_selection, talep_tipi, district)
        return

    finalize_talep_with_city(user_id, talep_tipi, district, df_ilce[df_ilce["District"] == district].iloc[0]["City"])


def handle_corrected_district(message, talep_tipi):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    corrected_district = message.text.strip().lower()

    if corrected_district == "değiştir":
        msg = bot.send_message(user_id, "Lütfen doğru ilçeyi yazın:")
        bot.register_next_step_handler(msg, process_district, talep_tipi)
    else:
        process_district(message, talep_tipi)


def handle_plaka_kodu(message, talep_tipi, district):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    plaka_kodu = message.text.strip()

    df_ilce = load_ilce_data()
    if df_ilce is None or plaka_kodu not in df_ilce["PlakaKodu"].tolist():
        msg = bot.send_message(user_id, "Geçersiz plaka kodu! Tekrar girin:")
        bot.register_next_step_handler(msg, handle_plaka_kodu, talep_tipi, district)
        return

    city_row = df_ilce[df_ilce["PlakaKodu"] == plaka_kodu]
    if city_row.empty:
        msg = bot.send_message(user_id, "Geçersiz plaka kodu! Tekrar girin:")
        bot.register_next_step_handler(msg, handle_plaka_kodu, talep_tipi, district)
        return

    city = city_row.iloc[0]["City"]
    finalize_talep_with_city(user_id, talep_tipi, district, city)


def handle_city_selection(message, talep_tipi, district):
    user_id = message.from_user.id
    log_user_input(user_id, message.text)
    selected_city = message.text.strip().lower()

    df_ilce = load_ilce_data()
    if df_ilce is None or selected_city not in df_ilce["City"].str.lower().tolist():
        msg = bot.send_message(user_id, "Geçersiz il! Tekrar seçin:")
        bot.register_next_step_handler(msg, handle_city_selection, talep_tipi, district)
        return

    finalize_talep_with_city(user_id, talep_tipi, district, selected_city)


def finalize_talep_with_city(user_id, talep_tipi, district, city):
    df_ilce = load_ilce_data()
    if df_ilce is None:
        bot.send_message(user_id, "İlçe bilgileri yüklenemedi.")
        return

    user_data = get_user_data(user_id)
    if user_data is None:
        bot.send_message(user_id, "Kullanıcı verileri bulunamadı.")
        return

    user_city = user_data["City"]
    user_district = user_data["District"]

    talep_edilen_vakif_row = df_ilce[(df_ilce["District"].str.lower() == district) & (df_ilce["City"].str.lower() == city)]
    if talep_edilen_vakif_row.empty:
        bot.send_message(user_id, "İlçe ve şehir bilgileri uyumsuz. Lütfen tekrar deneyin.")
        return

    talep_edilen_vakif_city = talep_edilen_vakif_row.iloc[0]["City"]
    phone = talep_edilen_vakif_row.iloc[0]["Phone"]
    ip_phone = talep_edilen_vakif_row.iloc[0]["IPPhone"]

    relevant_staff = get_relevant_staff(talep_edilen_vakif_city, district)
    if relevant_staff:
        staff_list = "\n".join([f'    <a href="tg://user?id={staff["UserID"]}" class="mention">@{staff["Username"] if pd.notna(staff["Username"]) else "Kullanıcı"}</a>'
                                for staff in relevant_staff])
    else:
        staff_list = "    Vakıf çalışanı bulunamadı"

    bot.send_message(-4639327269,
                     f"Transfer Talebi Var! 📢\n\n"
                     f"    👤 Talep Eden Vakıf: {user_city} - {user_district}\n"
                     f"    🏠 Talep Türü: {talep_tipi}\n"
                     f"    📍 Talep Edilen Vakıf: {talep_edilen_vakif_city} - {district}\n\n"
                     f"    ☎️ İletişim Bilgileri:\n"
                     f"    📞 Telefon: {phone}\n"
                     f"    📱 IP Telefon: {ip_phone}\n\n"
                     f"    📌 İlgili Vakıf Çalışanları:\n"
                     f"{staff_list}",
                     parse_mode="HTML")
    bot.send_message(user_id, "Talebiniz iletildi! ✅")


bot.polling()
