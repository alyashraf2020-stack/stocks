# ربط تيليجرام وإشعارات المتصفح

على Windows، اضبط قيم القنوات جوّه `environment` في `private.json` وأعد التشغيل بـ`RESTART.bat`. [الخطوات على Windows](WINDOWS_PERSONAL_SETUP.md#٣-التشغيل-اليومي-والإشعارات)

## تيليجرام

1. افتح [BotFather الرسمي](https://t.me/BotFather) واستخدم `/newbot` لبوت مخصص للتطبيق. احتفظ بالـtoken في ملف خدمة backend الخاص بصلاحية 0600.
2. عيّن `APP_HOST` باسم البوابة و`TELEGRAM_ENABLED=true` و`TELEGRAM_BOT_TOKEN`. استخدم مفتاح تشفير مستقل، واكتب ناتج `Fernet.generate_key()` في `NOTIFICATION_ENCRYPTION_KEY`. اربط رقم مستخدم تيليجرام في `TELEGRAM_OWNER_USER_ID` لو متاح وتريد تقييد المحادثة بحساب بعينه.
3. افتح `/settings/notifications` من بوابة HTTPS واضغط «ابدأ ربط جديد». افتح رابط البوت في محادثة خاصة واضغط Start، وارجع اضغط «تحقق من الربط» قبل مرور عشر دقايق. احتفظ بالرابط لنفسك لحد ما يتم استخدامه مرة واحدة. الربط بيتحقق من مرسل الرسالة ونوع المحادثة وصلاحية الكود. البوت يستخدم `getUpdates` للربط ويحتاج أن يكون مخصصًا للتطبيق بدون webhook أو قارئ updates تاني.
4. فعّل قناة تيليجرام واحفظ التفضيلات. شغّل `python -m app.workers.notification_worker` من `backend` بنفس قاعدة البيانات والبيئة الخاصة. بعدها اضغط «اختبار الإرسال» للوجهة. زر الاختبار بيضيف طلب للطابور، وسجل الإرسال يظهر نتيجة قبول طلب الإرسال عند تيليجرام.
5. لتعطيل القناة الغِ اختيارها واحفظ، ولإلغاء المحادثة اضغط «إلغاء الربط». لما تغيّر توكن البوت اعمل ربط جديد. خطأ من نوع 429 بيأجل محاولات القناة حسب الوقت اللي رجعه Telegram.

[Telegram Bot API](https://core.telegram.org/bots/api) · [حدود البوتات](https://core.telegram.org/bots/faq)

## Web Push

ولد زوج VAPID مرة واحدة في بيئة Python الخاصة بالـbackend. احفظ الناتج في ملف البيئة الخاص من غير نشره.

```python
import base64
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

key = generate_private_key(SECP256R1())
private = key.private_numbers().private_value.to_bytes(32, "big")
public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
for name, value in (("VAPID_PRIVATE_KEY", private), ("VAPID_PUBLIC_KEY", public)):
    print(name + "=" + base64.urlsafe_b64encode(value).decode().rstrip("="))
```

اكتب جهة اتصال صحيحة في `VAPID_SUBJECT`، مثل `mailto:owner@example.com`. عيّن `WEB_PUSH_ENABLED=true` و`NOTIFICATION_ENCRYPTION_KEY` و`APP_HOST`. أعد تشغيل الـAPI والعامل، وسجّل كل جهاز بإذن صريح من `/settings/devices`. فعّل قناة المتصفح من التفضيلات. المفتاح العام فقط متاح للواجهة. عند تغيير زوج المفاتيح، ألغِ اشتراك الجهاز القديم وسجّله من جديد.

اختبار التسليم الفعلي يحتاج جهازك وخادمك وتهيئة المفاتيح. الاختبارات البرمجية بتستخدم ردود نقل وهمية. التنبيه الافتراضي مناسب لشاشة القفل. الوضع التفصيلي بيضيف الرمز وتوقيت وطبيعة الرصد ضمن حقول محددة، وبيفضل عرض المحفظة الكاملة داخل البوابة.

التشغيل الشخصي على اللابتوب بيستخدم Telegram بالإرسال العادي في الحدود المجانية المعلنة للبوتات. تكلفة اتصال الإنترنت حسب خطتك الحالية. [حدود Telegram](https://core.telegram.org/bots/faq)
