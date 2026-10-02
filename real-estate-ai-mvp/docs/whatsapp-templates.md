# WhatsApp templates

EstraOS sends customer WhatsApp messages only through **approved templates**
(`WhatsAppService`), and only to a lead who said yes on a call (`whatsappConsent` with
`whatsappConsentAt` on the lead). Create these three templates in Meta Business Manager →
WhatsApp Manager → Message templates, category **Utility**, once per language. The template
name is the same in every language; the language code comes from `WHATSAPP_TEMPLATE_LANG_MAP`
(default `{"en":"en","hi":"hi","mr":"mr","gu":"gu"}`). Parameter numbers must stay in this
order: the code fills them positionally.

| Template | Sent when | Header | Body parameters |
| --- | --- | --- | --- |
| `visit_confirmation` | After a call that booked or rescheduled a visit, if the customer agreed | none | 1 customer name · 2 project · 3 date and time (IST) · 4 address · 5 map link · 6 agent name · 7 agent phone |
| `visit_reminder` | With the day-before reminder call (18:00 IST by default) | none | 1 customer name · 2 project · 3 date and time (IST) · 4 address · 5 agent name · 6 agent phone |
| `brochure_share` | After a call where the customer asked for the brochure | **Document** (the project's published brochure PDF, uploaded through the Cloud API media endpoint) | 1 customer name · 2 project |

Example values Meta asks for when you submit: `Asha`, `Sahyadri Grove`,
`Saturday, 10 Oct 2026 at 11:00 AM IST`, `Baner, Pune`, `https://maps.google.com/?q=Sahyadri+Grove`,
`Riya Desai`, `+91 98765 43210`.

## `visit_confirmation`

- **en** — Hi {{1}}, your site visit to {{2}} is confirmed for {{3}}. Address: {{4}}. Directions: {{5}}. Your property expert {{6}} ({{7}}) will meet you there. Reply STOP to opt out.
- **hi** — नमस्ते {{1}}, {{2}} की आपकी साइट विज़िट {{3}} के लिए कन्फ़र्म है। पता: {{4}}। रास्ता: {{5}}। आपके प्रॉपर्टी एक्सपर्ट {{6}} ({{7}}) वहाँ आपसे मिलेंगे। संदेश बंद करने के लिए STOP लिखें।
- **mr** — नमस्कार {{1}}, {{2}} ची तुमची साइट व्हिजिट {{3}} साठी निश्चित झाली आहे. पत्ता: {{4}}. नकाशा: {{5}}. तुमचे प्रॉपर्टी एक्सपर्ट {{6}} ({{7}}) तिथे तुम्हाला भेटतील. संदेश बंद करण्यासाठी STOP लिहा.
- **gu** — નમસ્તે {{1}}, {{2}} ની તમારી સાઇટ વિઝિટ {{3}} માટે કન્ફર્મ છે. સરનામું: {{4}}. રસ્તો: {{5}}. તમારા પ્રોપર્ટી એક્સપર્ટ {{6}} ({{7}}) ત્યાં તમને મળશે. સંદેશ બંધ કરવા STOP લખો.

## `visit_reminder`

- **en** — Hi {{1}}, a reminder of your visit to {{2}} on {{3}} at {{4}}. {{5}} ({{6}}) will be waiting for you. Need to change the time? Just reply here or call us.
- **hi** — नमस्ते {{1}}, याद दिला दें कि {{2}} की आपकी विज़िट {{3}} को {{4}} पर है। {{5}} ({{6}}) आपका इंतज़ार करेंगे। समय बदलना हो तो यहीं जवाब दें या हमें कॉल करें।
- **mr** — नमस्कार {{1}}, आठवण: {{2}} ची तुमची व्हिजिट {{3}} रोजी {{4}} येथे आहे. {{5}} ({{6}}) तुमची वाट पाहतील. वेळ बदलायची असल्यास इथे उत्तर द्या किंवा आम्हाला कॉल करा.
- **gu** — નમસ્તે {{1}}, યાદ અપાવીએ કે {{2}} ની તમારી વિઝિટ {{3}} એ {{4}} ખાતે છે. {{5}} ({{6}}) તમારી રાહ જોશે. સમય બદલવો હોય તો અહીં જવાબ આપો અથવા અમને કૉલ કરો.

## `brochure_share` (header: Document)

- **en** — Hi {{1}}, as promised on our call, here is the brochure for {{2}}. Happy to answer any questions or arrange a site visit.
- **hi** — नमस्ते {{1}}, कॉल पर बताए अनुसार यह रहा {{2}} का ब्रोशर। कोई भी सवाल हो या साइट विज़िट तय करनी हो तो बताइए।
- **mr** — नमस्कार {{1}}, कॉलवर सांगितल्याप्रमाणे {{2}} चे ब्रोशर पाठवत आहोत. काही प्रश्न असतील किंवा साइट व्हिजिट ठरवायची असेल तर कळवा.
- **gu** — નમસ્તે {{1}}, કૉલ પર કહ્યા મુજબ {{2}} નું બ્રોશર મોકલીએ છીએ. કોઈ પ્રશ્ન હોય કે સાઇટ વિઝિટ ગોઠવવી હોય તો જણાવો.

## Configuration

| Variable | Meaning |
| --- | --- |
| `WHATSAPP_PHONE_NUMBER_ID` | The Cloud API phone number id (numeric, not the phone number). Blank disables sending. |
| `WHATSAPP_ACCESS_TOKEN` | A permanent system-user token with `whatsapp_business_messaging`. |
| `WHATSAPP_API_VERSION` | Graph API version, e.g. `v21.0`. |
| `WHATSAPP_TEMPLATE_LANG_MAP` | Lead language → template language code. |
| `WHATSAPP_APP_SECRET` | The Meta app secret, used to verify `X-Hub-Signature-256` on the status webhook. |
| `WHATSAPP_VERIFY_TOKEN` | Any random string; enter the same value when subscribing the webhook. |
| `WHATSAPP_OFFICE_PHONE` | Spoken in messages when the assigned agent has no phone on file. |

Status webhook: subscribe the WhatsApp Business Account's `messages` field to
`https://<crm-api>/api/v1/webhooks/whatsapp`. Delivery states (sent, delivered, read, failed) update
the matching notification and add a `notification_deliveries` row.
