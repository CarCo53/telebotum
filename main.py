import telebot
import pandas as pd
import os

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


# 📌 Excel'den veri yükleme
def load_ilce_data():
    return pd.read_excel(ILCE_BILGILERI_PATH, dtype={"PlakaKodu": str})


# 📌 Kullanıcı kayıt kontrolü
def get_user_data(user_id):
    if os.path.exists(USER_DATA_PATH):
        df = pd.read_excel(USER_DATA_PATH)
        user_row = df[df["UserID"] == user_id]
        if not user_row.empty:
            return user_row.iloc[0]
    return None


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


# 📌 Kullanıcı bilgilerinin güncellenmesi
def update_user_data(message):
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
    plaka_kodu = message.text.strip()
    df = load_ilce_data()

    if plaka_kodu not in df["PlakaKodu"].values:
        msg = bot.send_message(user_id, "Geçersiz plaka kodu! Tekrar girin:")
        bot.register_next_step_handler(msg, ask_district)
        return

    # İlçeleri listele ve butonlarla sun
    available_districts = df[df["PlakaKodu"] == plaka_kodu]["District"].unique()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for district in available_districts:
        markup.add(district)

    msg = bot.send_message(user_id, "Lütfen ilçenizi seçin:", reply_markup=markup)
    bot.register_next_step_handler(msg, ask_contact_permission, plaka_kodu)


# 📌 Kullanıcıdan iletişim izni iste
def ask_contact_permission(message, plaka_kodu):
    user_id = message.from_user.id
    selected_district = message.text.strip()

    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Evet", "Hayır")

    msg = bot.send_message(user_id, "İletişime geçilmesine izin veriyor musunuz?", reply_markup=markup)
    bot.register_next_step_handler(msg, finalize_registration, plaka_kodu, selected_district)


# 📌 Kaydı tamamla
def finalize_registration(message, plaka_kodu, district):
    user_id = message.from_user.id
    username = message.from_user.username
    permission = message.text.strip()

    df = load_ilce_data()
    city = df[df["District"] == district]["City"].values[0]

    save_user_data(user_id, username, city, district, permission)
    bot.send_message(user_id, "Kayıt tamamlandı! Artık /talep komutunu kullanabilirsiniz. ✅")


# 📌 /talep komutu
@bot.message_handler(commands=["talep"])
def handle_talep(message):
    user_id = message.from_user.id

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
    bot.register_next_step_handler(msg, ask_district_for_talep)


# 📌 Talep için ilçe girme
def ask_district_for_talep(message):
    user_id = message.from_user.id
    talep_tipi = message.text.strip()

    msg = bot.send_message(user_id, "Lütfen ilçeyi girin:")
    bot.register_next_step_handler(msg, finalize_talep, talep_tipi)


# 📌 Talebi tamamla ve gruba ilet
def finalize_talep(message, talep_tipi):
    user_id = message.from_user.id
    district = message.text.strip()

    df = load_ilce_data()
    if district not in df["District"].values:
        bot.send_message(user_id, "Hatalı ilçe girdiniz! Lütfen doğru ilçeyi yazın.")
        return

    bot.send_message(-4639327269,
                     f"📢 **Transfer Talebi Var!** 📢\n🏠 **Talep Türü:** {talep_tipi}\n📍 **Talep Edilen İlçe:** {district}")
    bot.send_message(user_id, "Talebiniz iletildi! ✅")


bot.polling()