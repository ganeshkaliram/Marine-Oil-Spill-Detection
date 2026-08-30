export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { question } = req.body;

    if (!question) {
        return res.status(400).json({ error: 'Question is required' });
    }

    const apiKey = process.env.NVIDIA_API_KEY;

    if (!apiKey) {
        return res.status(500).json({ error: 'API key not configured' });
    }

    try {
        const response = await fetch(
            'https://integrate.api.nvidia.com/v1/chat/completions',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`
                },
                body: JSON.stringify({
                    model: 'meta/llama-3.1-8b-instruct',
                    messages: [
                        {
                            role: 'system',
                            content: 'You MUST respond with valid JSON only. No markdown, no code blocks, no explanation text. Just the raw JSON object. Keep code short (max 10 lines per language). Keep steps to 5-8 max. Use only ASCII characters.'
                        },
                        {
                            role: 'user',
                            content: `Return a JSON object for this algorithm question. Format:
{"name":"Name","category":"Cat","difficulty":"Easy|Medium|Hard","time":"O(n)","space":"O(1)","description":"One line desc","keywords":["k1","k2"],"code":{"python":["line1"],"javascript":["line1"],"java":["line1"]},"steps":[{"desc":"step desc","line":0,"state":{"var":"val"}}],"vizType":"array|sort|tree|linkedlist|graph","vizData":[1,2,3],"vizConfig":{"target":3}}

vizType options: array (for search), sort (for sorting), tree (for tree/recursive), linkedlist, graph
Keep code under 10 lines per language. 5-8 steps max. Use ASCII only (no special chars like squared symbol).

Question: ${question}`
                        }
                    ],
                    temperature: 0.3,
                    max_tokens: 12000
                })
            }
        );

        const data = await response.json();

        if (data.error) {
            return res.status(500).json({ error: data.error.message || 'API error' });
        }

        const content = data.choices?.[0]?.message?.content || data.choices?.[0]?.text;

        if (!content) {
            return res.status(500).json({ error: 'No response from AI', raw: JSON.stringify(data) });
        }

        let parsed;
        try {
            parsed = tryParseJSON(content);
        } catch (parseErr) {
            return res.status(500).json({ 
                error: 'Failed to parse AI response', 
                raw: content.substring(0, 1000),
                parseError: parseErr.message 
            });
        }

        return res.status(200).json(parsed);

    } catch (err) {
        return res.status(500).json({ error: err.message });
    }
}

function tryParseJSON(content) {
    // Try direct parse first
    try {
        return JSON.parse(content);
    } catch (e) {}

    // Remove markdown code blocks
    let cleaned = content;
    cleaned = cleaned.replace(/```json\s*/gi, '').replace(/```\s*/gi, '');
    cleaned = cleaned.trim();
    try {
        return JSON.parse(cleaned);
    } catch (e) {}

    // Extract JSON using balanced brace matching
    const json = extractJSON(cleaned);
    if (json) {
        try {
            return JSON.parse(json);
        } catch (e) {
            // Try to repair common JSON issues
            const repaired = repairJSON(json);
            if (repaired) {
                try {
                    return JSON.parse(repaired);
                } catch (e2) {}
            }
        }
    }

    throw new Error('Could not parse JSON from AI response');
}

function repairJSON(str) {
    let fixed = str;
    
    // Fix unquoted string values in arrays
    fixed = fixed.replace(/:\s*"([^"]*)"(\[[^\]]*\])/g, ': "$1$2"');
    
    // Fix missing commas between array elements that are strings
    fixed = fixed.replace(/"([^"]*)"\s*\n\s*"/g, '", "');
    
    // Remove trailing commas before ] or }
    fixed = fixed.replace(/,\s*([}\]])/g, '$1');
    
    // Fix escaped quotes inside strings
    fixed = fixed.replace(/\\'/g, "'");
    
    return fixed;
}

function extractJSON(str) {
    let depth = 0;
    let start = -1;
    for (let i = 0; i < str.length; i++) {
        if (str[i] === '{') {
            if (depth === 0) start = i;
            depth++;
        } else if (str[i] === '}') {
            depth--;
            if (depth === 0 && start >= 0) {
                return str.substring(start, i + 1);
            }
        }
    }
    return null;
}
