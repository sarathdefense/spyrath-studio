import menuData from "@/data/menu.json";

const RESTAURANT_INFO = `
TAAZA MART - AUTHENTIC INDIAN FOOD
Address: 6260 Commerce Palms Dr, Tampa, FL 33647
Phone: (813) 564-8100
Order Online: order.toasttab.com/online/taazamart
Facebook: facebook.com/taazamartfl
Hours: Open daily - closes at 9PM
Wednesday Special: Indo Chinese dishes at special prices every Wednesday!
`.trim();

function findRelevantCategories(question) {
  const q = question.toLowerCase();
  const relevant = [];
  for (const [key, category] of Object.entries(menuData.categories)) {
    if (category.keywords.some(kw => q.includes(kw.toLowerCase()))) {
      relevant.push(category);
    }
  }
  if (relevant.length === 0) {
    return [
      menuData.categories.daily_menu,
      menuData.categories.rices,
      menuData.categories.south_indian,
    ];
  }
  return relevant;
}

function formatCategory(category) {
  const items = category.items.map(item => {
    const desc = item.desc ? ` - ${item.desc}` : "";
    return `  - ${item.name}${desc}: $${item.price.toFixed(2)}`;
  }).join("\n");
  return `${category.label}:\n${items}`;
}

function buildMenuContext(question) {
  const categories = findRelevantCategories(question);
  const menuText = categories.map(formatCategory).join("\n\n");
  return `${RESTAURANT_INFO}\n\nRELEVANT MENU ITEMS:\n${menuText}\n\nFor the complete menu visit: order.toasttab.com/online/taazamart`;
}

export async function POST(req) {
  try {
    const { messages } = await req.json();
    if (!messages?.length) return new Response("Messages required", { status: 400 });

    const latestUser = [...messages].reverse().find(m => m.role === "user")?.content || "";
    const menuContext = buildMenuContext(latestUser);

    const systemPrompt = `You are the AI assistant for Taaza Mart, an authentic Indian restaurant in Tampa, Florida. You help customers with menu questions, hours, ordering, and anything about the restaurant.

${menuContext}

INSTRUCTIONS:
- Answer questions about the menu, hours, location, pricing, and ingredients warmly and helpfully.
- For ordering, always direct customers to [Order Online](https://order.toasttab.com/online/taazamart)
- Format phone as clickable: [(813) 564-8100](tel:8135648100)
- Highlight the Wednesday Indo Chinese Specials when relevant — great value!
- If asked about combos, explain they include dal curry + choice of curry + white rice + 2pc chapati.
- If asked about spice levels, explain most dishes can be adjusted.
- If asked about vegetarian options, highlight the extensive veg menu.
- Be warm, friendly, and helpful — like a knowledgeable restaurant staff member.
- Keep responses concise and practical.
- If asked about something unrelated to the restaurant, politely say: "I'm the Taaza Mart assistant — I can help with our menu, hours, or ordering! Is there anything about Taaza Mart I can help you with?"
- If a dish is not in the menu above, say: "That may be on our full menu — check [order.toasttab.com/online/taazamart](https://order.toasttab.com/online/taazamart) or call us at [(813) 564-8100](tel:8135648100)"
- Never fabricate prices or dishes not shown above.
- End responses with 2 suggested follow-up questions in this exact format:
<suggestions>
Question one?
Question two?
</suggestions>`;

    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${process.env.GROQ_API_KEY}`,
      },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        stream: true,
        max_tokens: 1500,
        temperature: 0.4,
        messages: [
          { role: "system", content: systemPrompt },
          ...messages.slice(-6),
        ],
      }),
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Groq error: ${err}`);
    }

    return new Response(res.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  } catch (err) {
    console.error("[/api/chat] ERROR:", err.message);
    return new Response(
      JSON.stringify({ error: "I'm temporarily unavailable. Please call us at (813) 564-8100 or visit order.toasttab.com/online/taazamart" }),
      { status: 500 }
    );
  }
}
