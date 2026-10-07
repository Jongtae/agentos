# Conversation image localization

The built-in image-generation edit tool used [`owner-pilot-conversation-edited.png`](owner-pilot-conversation-edited.png) as the edit target for four 1536 × 1024 PNGs. The untouched owner-supplied source remains [`owner-pilot-conversation-reference.jpg`](owner-pilot-conversation-reference.jpg). The localized images are illustrative reconstructions, not product captures or evidence of shipped integrations.

## Final prompt set

Each language edit was prompted to retain the three realistic phone screens, green interface, avatars, photos, map, product and place cards, relative placement, and footer evidence boundary. It was told to translate **all visible text** into the target language, including headings, subtitles, dialogue, card labels, login button, input placeholder and footer; to keep text legible and inside cards; and to avoid a completed purchase or claim of a live integration. The Korean edit specifically preserved the existing Korean dialogue while translating the remaining English headings, tagline, placeholders and footer.

| Locale and file | Key dialogue and labels requested |
| --- | --- |
| [`en`](owner-pilot-conversation.en.png) | “Heading home. Dinner on the way?” → request location → route options with distance/open status; belt photo → three priced options → ask for shopping-account login before cart action; restaurant photo → walk/café/bar → check route and hours. Footer: “Illustrative reconstruction based on real owner-pilot conversations. Condensed and redacted; not a verbatim product screenshot.” |
| [`ko`](owner-pilot-conversation.ko.png) | Existing Korean conversations retained. Headings “집으로 가는 길”, “이거 찾아줘”, “지금 여기야. 다음은?”; Korean subtitle, input labels and footer: “실제 오너 파일럿 대화를 바탕으로 요약·익명화한 설명용 재구성입니다. 제품 화면 그대로의 캡처는 아닙니다.” |
| [`ja`](owner-pilot-conversation.ja.png) | “帰り道、夕食どうしよう？” → 現在地を共有 → 焼肉・イタリアン・和食; belt photo → three priced options → “続けるには買い物用アカウントへのログインが必要です。”; restaurant photo → 公園を散歩・カフェ・バー → 道順と営業時間を確認. Footer identifies an abridged, anonymized illustrative reconstruction rather than a product capture. |
| [`zh-CN`](owner-pilot-conversation.zh-CN.png) | “回家路上，晚饭吃什么？” → 分享位置 → 韩式烤肉・意式餐厅・韩式套餐; belt photo → three priced options → “继续之前，需要登录您的购物账户。”; restaurant photo → 公园散步・咖啡馆・酒吧 → 核对路线和营业时间. Footer identifies an abridged, anonymized illustrative reconstruction rather than a product capture. |

The image text and layout were visually checked at full resolution. README captions, alt text and scene-by-scene prose carry the same meaning when the image is downscaled on mobile.
