let currentAlgorithm = null;
let currentLang = 'python';
let isPlaying = false;
let animationTimer = null;
let currentStep = 0;
let animationSteps = [];
let speed = 2000;

const canvas = document.getElementById('vizCanvas');
const ctx = canvas.getContext('2d');

function resizeCanvas() {
    const wrapper = canvas.parentElement;
    canvas.width = wrapper.clientWidth;
    canvas.height = 400;
    if (currentAlgorithm && currentStep > 0) {
        drawVisualization(animationSteps[currentStep - 1]);
    }
}

window.addEventListener('resize', resizeCanvas);
resizeCanvas();

const searchInput = document.getElementById('searchInput');
const resultsSection = document.getElementById('resultsSection');
const featuresSection = document.getElementById('featuresSection');
const browseSection = document.getElementById('browseSection');
const hero = document.querySelector('.hero');

searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') performSearch();
});

document.querySelectorAll('.quick-tag').forEach(tag => {
    tag.addEventListener('click', () => {
        searchInput.value = tag.dataset.query;
        performSearch();
    });
});

document.getElementById('backBtn').addEventListener('click', showHome);
document.getElementById('playBtn').addEventListener('click', playAnimation);
document.getElementById('pauseBtn').addEventListener('click', pauseAnimation);
document.getElementById('stepBtn').addEventListener('click', stepForward);
document.getElementById('resetBtn').addEventListener('click', resetAnimation);

document.getElementById('speedSelect').addEventListener('change', (e) => {
    speed = parseInt(e.target.value);
});

document.querySelectorAll('.code-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentLang = tab.dataset.lang;
        if (currentAlgorithm) renderCode(currentAlgorithm);
    });
});

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    const results = algorithms.filter(algo => {
        const q = query.toLowerCase();
        return algo.name.toLowerCase().includes(q) ||
               algo.category.toLowerCase().includes(q) ||
               algo.keywords.some(k => k.includes(q));
    });

    if (results.length > 0) {
        showResult(results[0]);
        return;
    }

    showLoadingState(query);

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: query })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'API request failed');
        }

        const aiResult = await response.json();
        const algo = convertAIResult(aiResult, query);
        showResult(algo);

    } catch (err) {
        console.error('AI API error:', err);
        alert('Could not analyze question: ' + err.message + '\n\nTry one of the pre-built algorithms: binary search, two sum, bubble sort, fibonacci, bfs, dfs, linked list, merge sort, quick sort.');
        showHome();
    }
}

function showLoadingState(query) {
    hero.style.display = 'none';
    featuresSection.style.display = 'none';
    browseSection.style.display = 'none';
    resultsSection.style.display = 'block';
    document.getElementById('resultTitle').textContent = query;
    document.getElementById('analysisText').textContent = 'Analyzing with AI... Please wait.';
    document.getElementById('difficultyBadge').textContent = '...';
    document.getElementById('timeBadge').textContent = '...';
    document.getElementById('lineNumbers').innerHTML = '';
    document.getElementById('codeContent').innerHTML = '<span style="color:#6b6b80">Generating code...</span>';
    document.getElementById('traceLog').innerHTML = '';
    document.getElementById('stepDescription').textContent = 'AI is generating visualization...';

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    ctx.fillStyle = '#DA7014';
    ctx.font = '600 16px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('Analyzing with AI...', cx, cy - 10);
    ctx.fillStyle = '#a0a0b5';
    ctx.font = '400 13px Inter';
    ctx.fillText('Generating visualization for: ' + query, cx, cy + 15);

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function convertAIResult(ai, originalQuery) {
    const codeLines = {};
    ['python', 'javascript', 'java'].forEach(lang => {
        const lines = ai.code?.[lang] || [];
        codeLines[lang] = lines.map(line => {
            const tokens = [];
            const str = line;
            const patterns = [
                { regex: /(#[^\n]*|\/\/[^\n]*)/, type: 'comment' },
                { regex: /\b(def|function|class|if|else|elif|else if|for|while|return|import|from|let|const|var|new|public|private|void|int|string|boolean|True|False|None|null|undefined|in|not|and|or|try|catch|finally|throw|break|continue|switch|case|default|do|this|super|extends|implements|static|final|abstract|interface)\b/, type: 'keyword' },
                { regex: /\b(\d+\.?\d*)\b/, type: 'number' },
                { regex: /(["'`])(?:(?!\1|\\).|\\.)*\1/, type: 'string' },
                { regex: /\b([A-Z]\w*)\b/, type: 'type' },
                { regex: /(\w+)\s*\(/, type: 'function' },
                { regex: /([=+\-*/<>!&|^~%]+)/, type: 'operator' },
            ];

            let remaining = str;
            let pos = 0;
            const parts = [];

            while (pos < str.length) {
                let earliest = null;
                let earliestType = '';
                let earliestIdx = str.length;

                for (const p of patterns) {
                    const m = str.slice(pos).match(p.regex);
                    if (m && m.index < earliestIdx) {
                        earliest = m;
                        earliestType = p.type;
                        earliestIdx = m.index;
                    }
                }

                if (earliest && earliestIdx < str.length) {
                    if (earliestIdx > 0) {
                        parts.push({ type: 'plain', val: str.slice(pos, pos + earliestIdx) });
                    }
                    parts.push({ type: earliestType, val: earliest[0] });
                    pos += earliestIdx + earliest[0].length;
                } else {
                    parts.push({ type: 'plain', val: str.slice(pos) });
                    break;
                }
            }

            return { text: line, tokens: parts.length ? parts : [{ type: 'plain', val: line || ' ' }] };
        });
    });

    const steps = (ai.steps || []).map((s, i) => ({
        type: ai.vizType || 'array',
        data: [...(ai.vizData || [1,2,3,4,5])],
        line: s.line || 0,
        desc: s.desc || `Step ${i + 1}`,
        state: s.state || {}
    }));

    return {
        id: 'ai-' + Date.now(),
        name: ai.name || originalQuery,
        category: ai.category || 'General',
        difficulty: ai.difficulty || 'Medium',
        time: ai.time || 'O(n)',
        description: ai.description || `AI-generated analysis for: ${originalQuery}`,
        keywords: ai.keywords || [originalQuery.toLowerCase()],
        vizType: ai.vizType || 'array',
        vizData: ai.vizData || [1, 2, 3, 4, 5],
        target: ai.vizConfig?.target || ai.vizConfig?.searchTarget,
        code: codeLines,
        aiSteps: steps,
        isAI: true
    };
}

function showResult(algo) {
    currentAlgorithm = algo;
    hero.style.display = 'none';
    featuresSection.style.display = 'none';
    browseSection.style.display = 'none';
    resultsSection.style.display = 'block';

    document.getElementById('resultTitle').textContent = algo.name;
    document.getElementById('analysisText').textContent = algo.description;
    document.getElementById('difficultyBadge').textContent = algo.difficulty;
    document.getElementById('timeBadge').textContent = algo.time;

    renderCode(algo);
    generateAnimationSteps(algo);
    resetAnimation();
    resizeCanvas();

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showHome() {
    hero.style.display = '';
    featuresSection.style.display = '';
    browseSection.style.display = '';
    resultsSection.style.display = 'none';
    pauseAnimation();
    currentAlgorithm = null;
}

function renderCode(algo) {
    const codeLines = algo.code[currentLang] || algo.code.python;
    const lineNumbers = document.getElementById('lineNumbers');
    const codeContent = document.getElementById('codeContent');

    lineNumbers.innerHTML = codeLines.map((_, i) => `<div>${i + 1}</div>`).join('');

    codeContent.innerHTML = codeLines.map((line, i) => {
        const tokensHtml = line.tokens.map(t => {
            if (t.type === 'comment') return `<span class="code-comment">${escHtml(t.val)}</span>`;
            return `<span class="code-${t.type}">${escHtml(t.val)}</span>`;
        }).join('');
        return `<span class="code-line" data-line="${i}">${tokensHtml || '&nbsp;'}</span>`;
    }).join('\n');
}

function escHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function generateAnimationSteps(algo) {
    animationSteps = [];

    if (algo.isAI && algo.aiSteps && algo.aiSteps.length > 0) {
        animationSteps = algo.aiSteps.map((step, idx) => {
            const data = step.data || [...algo.vizData];
            const vizType = algo.vizType || 'array';
            const desc = (step.desc || '').toLowerCase();
            const state = step.state || {};

            const enriched = {
                ...step,
                data: data,
                target: algo.target
            };

            if (vizType === 'sort' || desc.includes('sort') || desc.includes('swap') || desc.includes('compare')) {
                enriched.type = 'sort';
                enriched.comparing = undefined;
                enriched.swapping = undefined;
                enriched.sorted = [];

                const arrIdx = (v) => {
                    if (typeof v === 'number' && v >= 0 && v < data.length) return v;
                    return undefined;
                };

                if (state.i !== undefined && state.j !== undefined) {
                    enriched.comparing = [arrIdx(state.i), arrIdx(state.j)].filter(x => x !== undefined);
                } else if (state.minIdx !== undefined && state.j !== undefined) {
                    enriched.comparing = [arrIdx(state.minIdx), arrIdx(state.j)].filter(x => x !== undefined);
                } else if (state.left !== undefined && state.right !== undefined) {
                    enriched.comparing = [arrIdx(state.left), arrIdx(state.right)].filter(x => x !== undefined);
                }

                if (desc.includes('swap')) {
                    enriched.swapping = enriched.comparing;
                    enriched.comparing = undefined;
                }

                if (desc.includes('sorted') || desc.includes('placed') || desc.includes('complete')) {
                    enriched.sorted = data.map((_, i) => i);
                } else if (state.sorted) {
                    enriched.sorted = Array.isArray(state.sorted) ? state.sorted : [];
                }
            } else if (vizType === 'tree' || desc.includes('recursive') || desc.includes('fibonacci') || desc.includes('fib')) {
                enriched.type = 'tree';
                enriched.node = state.node || state.current || `node-${idx}`;
                enriched.val = state.result !== undefined ? state.result : (state.val !== undefined ? state.val : null);
                enriched.depth = state.depth !== undefined ? state.depth : Math.min(idx, 4);
            } else if (vizType === 'linkedlist' || desc.includes('linked') || desc.includes('node') || desc.includes('reverse')) {
                enriched.type = 'linkedlist';
                enriched.currentIdx = state.index !== undefined ? state.index : (state.current !== undefined ? state.current : idx % data.length);
                enriched.reversedIdx = idx;
                enriched.prevData = state.prev || null;
            } else if (vizType === 'graph' || desc.includes('visit') || desc.includes('traverse') || desc.includes('bfs') || desc.includes('dfs')) {
                enriched.type = 'graph';
                enriched.nodes = algo.vizData;
                enriched.edges = algo.vizConfig?.edges || [];
                enriched.visited = state.visited || [];
                enriched.current = state.current || state.node;
                enriched.queue = state.queue || state.stack || [];
            } else {
                enriched.type = 'search';
                const idxVal = state.index !== undefined ? state.index : (state.i !== undefined ? state.i : undefined);
                enriched.comparing = arrIdx(idxVal);
                enriched.found = desc.includes('found') || desc.includes('return');
                enriched.target = algo.target;

                function arrIdx(v) {
                    if (typeof v === 'number' && v >= 0 && v < data.length) return v;
                    return undefined;
                }
            }

            return enriched;
        });
        return;
    }

    const data = [...algo.vizData];

    switch (algo.vizType) {
        case 'array':
            if (algo.target !== undefined) {
                generateBinarySearchSteps(algo, data);
            } else {
                generateLinearSearchSteps(algo, data);
            }
            break;
        case 'array-pair':
            generateTwoSumSteps(algo, data);
            break;
        case 'sort':
            generateSortSteps(algo, data);
            break;
        case 'tree':
            generateFibSteps(algo, data);
            break;
        case 'linkedlist':
            generateLinkedListSteps(algo, data);
            break;
        case 'graph':
            generateGraphSteps(algo, data);
            break;
        case 'binary':
            generateBinarySteps(algo, data);
            break;
        default:
            generateLinearSearchSteps(algo, data);
            break;
    }
}

function generateBinarySearchSteps(algo, data) {
    const target = algo.target;
    let left = 0;
    let right = data.length - 1;

    animationSteps.push({
        type: 'binary-search',
        data: [...data],
        left: left,
        right: right,
        mid: -1,
        found: false,
        target: target,
        line: 1,
        desc: `Initialize left=0, right=${right}`
    });

    while (left <= right) {
        const mid = Math.floor((left + right) / 2);
        animationSteps.push({
            type: 'binary-search',
            data: [...data],
            left: left,
            right: right,
            mid: mid,
            found: false,
            target: target,
            line: 3,
            desc: `Calculate mid = (${left} + ${right}) / 2 = ${mid}`
        });

        if (data[mid] === target) {
            animationSteps.push({
                type: 'binary-search',
                data: [...data],
                left: left,
                right: right,
                mid: mid,
                found: true,
                target: target,
                line: 4,
                desc: `Found ${target} at index ${mid}!`
            });
            return;
        } else if (data[mid] < target) {
            animationSteps.push({
                type: 'binary-search',
                data: [...data],
                left: left,
                right: right,
                mid: mid,
                found: false,
                target: target,
                line: 6,
                desc: `arr[${mid}]=${data[mid]} < ${target}, search right half`
            });
            left = mid + 1;
            animationSteps.push({
                type: 'binary-search',
                data: [...data],
                left: left,
                right: right,
                mid: -1,
                found: false,
                target: target,
                line: 7,
                desc: `Update left = ${left}`
            });
        } else {
            animationSteps.push({
                type: 'binary-search',
                data: [...data],
                left: left,
                right: right,
                mid: mid,
                found: false,
                target: target,
                line: 8,
                desc: `arr[${mid}]=${data[mid]} > ${target}, search left half`
            });
            right = mid - 1;
            animationSteps.push({
                type: 'binary-search',
                data: [...data],
                left: left,
                right: right,
                mid: -1,
                found: false,
                target: target,
                line: 9,
                desc: `Update right = ${right}`
            });
        }
    }

    animationSteps.push({
        type: 'binary-search',
        data: [...data],
        left: left,
        right: right,
        mid: -1,
        found: false,
        target: target,
        line: 10,
        desc: `Target ${target} not found in array.`
    });
}

function generateLinearSearchSteps(algo, data) {
    for (let i = 0; i < data.length; i++) {
        animationSteps.push({
            type: 'search',
            data: [...data],
            comparing: i,
            found: false,
            target: undefined,
            line: i,
            desc: `Processing element arr[${i}] = ${data[i]}`
        });
    }
    animationSteps.push({
        type: 'search',
        data: [...data],
        comparing: -1,
        found: false,
        target: undefined,
        line: data.length,
        desc: 'Processing complete'
    });
}

function generateTwoSumSteps(algo, data) {
    const target = algo.target;
    const seen = {};
    for (let i = 0; i < data.length; i++) {
        const complement = target - data[i];
        const found = complement in seen;
        animationSteps.push({
            type: 'pair',
            data: [...data],
            currentIndex: i,
            complement: complement,
            found: found,
            pairIndex: found ? seen[complement] : -1,
            seen: {...seen},
            target: target,
            line: found ? 5 : 7,
            desc: found
                ? `Found pair! arr[${seen[complement]}]=${complement} + arr[${i}]=${data[i]} = ${target}`
                : `Checking arr[${i}]=${data[i]}, complement=${complement} not in seen`
        });
        if (found) return;
        seen[data[i]] = i;
    }
}

function generateSortSteps(algo, data) {
    const arr = [...data];
    const n = arr.length;
    let algoName = algo.id;

    if (algoName === 'bubble-sort') {
        for (let i = 0; i < n; i++) {
            for (let j = 0; j < n - i - 1; j++) {
                animationSteps.push({
                    type: 'sort',
                    data: [...arr],
                    comparing: [j, j + 1],
                    sorted: Array.from({length: i}, (_, k) => n - 1 - k),
                    line: 4,
                    desc: `Comparing arr[${j}]=${arr[j]} and arr[${j+1}]=${arr[j+1]}`
                });
                if (arr[j] > arr[j + 1]) {
                    const leftVal = arr[j];
                    const rightVal = arr[j + 1];
                    [arr[j], arr[j + 1]] = [arr[j + 1], arr[j]];
                    animationSteps.push({
                        type: 'sort',
                        data: [...arr],
                        swapping: [j, j + 1],
                        sorted: Array.from({length: i}, (_, k) => n - 1 - k),
                        line: 5,
                        desc: `Swapped ${leftVal} and ${rightVal}`
                    });
                }
            }
        }
    } else if (algoName === 'selection-sort') {
        for (let i = 0; i < n; i++) {
            let minIdx = i;
            for (let j = i + 1; j < n; j++) {
                animationSteps.push({
                    type: 'sort',
                    data: [...arr],
                    comparing: [minIdx, j],
                    sorted: Array.from({length: i}, (_, k) => k),
                    currentMin: minIdx,
                    line: 5,
                    desc: `Comparing current min arr[${minIdx}]=${arr[minIdx]} with arr[${j}]=${arr[j]}`
                });
                if (arr[j] < arr[minIdx]) minIdx = j;
            }
            if (minIdx !== i) {
                const oldMinVal = arr[minIdx];
                const oldIVal = arr[i];
                [arr[i], arr[minIdx]] = [arr[minIdx], arr[i]];
                animationSteps.push({
                    type: 'sort',
                    data: [...arr],
                    swapping: [i, minIdx],
                    sorted: Array.from({length: i + 1}, (_, k) => k),
                    line: 7,
                    desc: `Swapped arr[${i}]=${oldIVal} with minimum arr[${minIdx}]=${oldMinVal}`
                });
            }
        }
    } else if (algoName === 'insertion-sort') {
        for (let i = 1; i < n; i++) {
            const key = arr[i];
            let j = i - 1;
            animationSteps.push({
                type: 'sort',
                data: [...arr],
                inserting: i,
                sorted: Array.from({length: i}, (_, k) => k),
                line: 2,
                desc: `Inserting key=${key} into sorted portion`
            });
            while (j >= 0 && arr[j] > key) {
                animationSteps.push({
                    type: 'sort',
                    data: [...arr],
                    comparing: [j, j + 1],
                    sorted: Array.from({length: i}, (_, k) => k),
                    line: 4,
                    desc: `arr[${j}]=${arr[j]} > key=${key}, shifting right`
                });
                arr[j + 1] = arr[j];
                j--;
            }
            arr[j + 1] = key;
            animationSteps.push({
                type: 'sort',
                data: [...arr],
                inserted: j + 1,
                sorted: Array.from({length: i + 1}, (_, k) => k),
                line: 7,
                desc: `Placed key=${key} at position ${j + 1}`
            });
        }
    } else if (algoName === 'merge-sort') {
        generateMergeSortSteps(arr, 0, n - 1);
    } else if (algoName === 'quick-sort') {
        generateQuickSortSteps(arr, 0, n - 1);
    }

    animationSteps.push({
        type: 'sort',
        data: [...arr],
        sorted: Array.from({length: n}, (_, k) => k),
        line: algoName === 'bubble-sort' ? 6 : 8,
        desc: 'Sorting complete!'
    });
}

function generateMergeSortSteps(arr, left, right) {
    if (left >= right) return;
    const mid = Math.floor((left + right) / 2);
    generateMergeSortSteps(arr, left, mid);
    generateMergeSortSteps(arr, mid + 1, right);

    const temp = [];
    let i = left, j = mid + 1;

    animationSteps.push({
        type: 'sort',
        data: [...arr],
        range: [left, mid, right],
        line: 4,
        desc: `Merging subarrays [${left}..${mid}] and [${mid+1}..${right}]`
    });

    while (i <= mid && j <= right) {
        animationSteps.push({
            type: 'sort',
            data: [...arr],
            comparing: [i, j],
            range: [left, mid, right],
            line: 3,
            desc: `Comparing arr[${i}]=${arr[i]} and arr[${j}]=${arr[j]}`
        });
        if (arr[i] <= arr[j]) {
            temp.push(arr[i++]);
        } else {
            temp.push(arr[j++]);
        }
    }
    while (i <= mid) temp.push(arr[i++]);
    while (j <= right) temp.push(arr[j++]);

    for (let k = 0; k < temp.length; k++) {
        arr[left + k] = temp[k];
    }

    animationSteps.push({
        type: 'sort',
        data: [...arr],
        range: [left, mid, right],
        merged: true,
        line: 7,
        desc: `Merged: [${temp.join(', ')}]`
    });
}

function generateQuickSortSteps(arr, low, high) {
    if (low >= high) return;
    const pivotVal = arr[high];
    let i = low - 1;

    animationSteps.push({
        type: 'sort',
        data: [...arr],
        pivot: high,
        range: [low, high],
        line: 7,
        desc: `Pivot = ${pivotVal} at index ${high}`
    });

    for (let j = low; j < high; j++) {
        animationSteps.push({
            type: 'sort',
            data: [...arr],
            comparing: [j, high],
            pivot: high,
            range: [low, high],
            line: 10,
            desc: `Comparing arr[${j}]=${arr[j]} with pivot=${pivotVal}`
        });
        if (arr[j] <= pivotVal) {
            i++;
            if (i !== j) {
                [arr[i], arr[j]] = [arr[j], arr[i]];
                animationSteps.push({
                    type: 'sort',
                    data: [...arr],
                    swapping: [i, j],
                    pivot: high,
                    range: [low, high],
                    line: 12,
                    desc: `Swapped arr[${i}] and arr[${j}]`
                });
            }
        }
    }
    [arr[i + 1], arr[high]] = [arr[high], arr[i + 1]];
    animationSteps.push({
        type: 'sort',
        data: [...arr],
        swapping: [i + 1, high],
        pivotFinal: i + 1,
        line: 14,
        desc: `Pivot ${pivotVal} placed at its correct position ${i + 1}`
    });

    generateQuickSortSteps(arr, low, i);
    generateQuickSortSteps(arr, i + 2, high);
}

function generateFibSteps(algo, data) {
    const n = data[0];
    const tree = buildFibTree(n);
    flattenTree(tree, 0);
}

function buildFibTree(n) {
    if (n <= 1) return { val: n, left: null, right: null, id: `fib(${n})` };
    return {
        val: null,
        left: buildFibTree(n - 1),
        right: buildFibTree(n - 2),
        id: `fib(${n})`
    };
}

function flattenTree(node, depth) {
    if (!node) return;
    animationSteps.push({
        type: 'tree',
        node: node.id,
        val: node.val,
        depth: depth,
        line: node.val !== null ? 3 : 4,
        desc: node.val !== null
            ? `Base case: fib(${node.val}) = ${node.val}`
            : `Computing ${node.id} = fib(${parseInt(node.id.match(/\d+/)[0]) - 1}) + fib(${parseInt(node.id.match(/\d+/)[0]) - 2})`
    });
    flattenTree(node.left, depth + 1);
    flattenTree(node.right, depth + 1);
}

function generateLinkedListSteps(algo, data) {
    const n = data.length;
    let prev = null;
    let curr = [...data];

    for (let i = 0; i < n; i++) {
        animationSteps.push({
            type: 'linkedlist',
            data: [...curr],
            prevData: prev ? [...prev] : null,
            currentIdx: 0,
            reversedIdx: i,
            line: 9,
            desc: `Processing node with value ${curr[0]}`
        });

        const nextTemp = curr.slice(1);
        const newPrev = [curr[0], ...(prev || [])];
        prev = newPrev;
        curr = nextTemp;

        animationSteps.push({
            type: 'linkedlist',
            data: [...curr],
            prevData: prev ? [...prev] : null,
            currentIdx: curr.length > 0 ? 0 : -1,
            reversedIdx: i + 1,
            line: 11,
            desc: `Reversed pointer: ${prev[0]} now points to ${prev.length > 1 ? prev[1] : 'null'}`
        });
    }

    animationSteps.push({
        type: 'linkedlist',
        data: [],
        prevData: prev ? [...prev] : null,
        currentIdx: -1,
        reversedIdx: n,
        line: 14,
        desc: 'Linked list fully reversed!'
    });
}

function generateGraphSteps(algo, data) {
    const edges = data;
    const nodes = new Set();
    edges.forEach(e => { nodes.add(e[0]); nodes.add(e[1]); });
    const nodeList = [...nodes].sort((a, b) => a - b);
    const adjacency = {};
    nodeList.forEach(n => adjacency[n] = []);
    edges.forEach(e => { adjacency[e[0]].push(e[1]); adjacency[e[1]].push(e[0]); });

    const isDFS = algo.id === 'dfs';
    const visited = new Set();
    const queue = [0];
    visited.add(0);
    const visitOrder = [];

    while (queue.length > 0) {
        const node = isDFS ? queue.pop() : queue.shift();
        visitOrder.push(node);

        animationSteps.push({
            type: 'graph',
            adjacency: {...adjacency},
            nodes: nodeList,
            edges: [...edges],
            visited: [...visited],
            current: node,
            queue: [...queue],
            line: isDFS ? 4 : 5,
            desc: `Visiting node ${node}`
        });

        for (const neighbor of adjacency[node].sort((a, b) => a - b)) {
            if (!visited.has(neighbor)) {
                visited.add(neighbor);
                queue.push(neighbor);
                animationSteps.push({
                    type: 'graph',
                    adjacency: {...adjacency},
                    nodes: nodeList,
                    edges: [...edges],
                    visited: [...visited],
                    current: neighbor,
                    queue: [...queue],
                    discovered: neighbor,
                    line: isDFS ? 7 : 10,
                    desc: `Discovered node ${neighbor} from node ${node}`
                });
            }
        }
    }
}

function generateBinarySteps(algo, data) {
    const n = data[0];
    animationSteps.push({
        type: 'binary',
        value: n,
        bits: n.toString(2).split('').map(Number),
        line: 2,
        desc: `${n} in binary is ${n.toString(2)}`
    });

    const isPower = n > 0 && (n & (n - 1)) === 0;
    const nm1 = n - 1;
    const andResult = n & nm1;

    animationSteps.push({
        type: 'binary',
        value: n,
        bits: n.toString(2).split('').map(Number),
        nm1bits: nm1.toString(2).split('').map(Number),
        andResult: andResult,
        line: 2,
        desc: `${n} & ${nm1} = ${andResult} (must be 0 for power of two)`
    });

    animationSteps.push({
        type: 'binary',
        value: n,
        bits: n.toString(2).split('').map(Number),
        isPower: isPower,
        result: isPower,
        line: 2,
        desc: isPower ? `${n} IS a power of two!` : `${n} is NOT a power of two.`
    });
}

function playAnimation() {
    if (currentStep >= animationSteps.length) {
        currentStep = 0;
    }
    isPlaying = true;
    document.getElementById('playBtn').style.display = 'none';
    document.getElementById('pauseBtn').style.display = '';
    animate();
}

function animate() {
    if (!isPlaying || currentStep >= animationSteps.length) {
        pauseAnimation();
        return;
    }
    stepForward();
    animationTimer = setTimeout(animate, speed);
}

function pauseAnimation() {
    isPlaying = false;
    clearTimeout(animationTimer);
    document.getElementById('playBtn').style.display = '';
    document.getElementById('pauseBtn').style.display = 'none';
}

function stepForward() {
    if (currentStep >= animationSteps.length) return;
    const step = animationSteps[currentStep];
    currentStep++;
    drawVisualization(step);
    updateTrace(step);
    highlightCodeLine(step.line);
    document.getElementById('stepDescription').textContent = step.desc;
}

function resetAnimation() {
    pauseAnimation();
    currentStep = 0;
    document.getElementById('traceLog').innerHTML = '';
    document.getElementById('stepDescription').textContent = 'Press Play or Step to begin visualization';
    if (currentAlgorithm) {
        highlightCodeLine(-1);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        drawInitialVisualization(currentAlgorithm);
    }
}

function highlightCodeLine(lineIdx) {
    document.querySelectorAll('.code-line').forEach(el => {
        el.classList.remove('highlight');
    });
    if (lineIdx >= 0) {
        const el = document.querySelector(`.code-line[data-line="${lineIdx}"]`);
        if (el) {
            el.classList.add('highlight');
            el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }
}

function updateTrace(step) {
    const traceLog = document.getElementById('traceLog');
    const entry = document.createElement('div');
    entry.className = 'trace-entry';
    entry.innerHTML = `
        <span class="trace-step">#${currentStep}</span>
        <span class="trace-line">L${step.line + 1}</span>
        <span class="trace-content">${escHtml(step.desc)}</span>
    `;
    traceLog.appendChild(entry);
    traceLog.scrollTop = traceLog.scrollHeight;
}

function drawInitialVisualization(algo) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;

    ctx.fillStyle = '#DA7014';
    ctx.font = '600 16px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(`Ready to visualize: ${algo.name}`, cx, cy - 10);
    ctx.fillStyle = '#a0a0b5';
    ctx.font = '400 13px Inter';
    ctx.fillText('Press Play or Step to begin', cx, cy + 15);
}

function drawVisualization(step) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    switch (step.type) {
        case 'search':
        case 'pair':
            drawArrayViz(step);
            break;
        case 'binary-search':
            drawBinarySearchViz(step);
            break;
        case 'sort':
            drawSortViz(step);
            break;
        case 'tree':
            drawTreeViz(step);
            break;
        case 'linkedlist':
            drawLinkedListViz(step);
            break;
        case 'graph':
            drawGraphViz(step);
            break;
        case 'binary':
            drawBinaryViz(step);
            break;
        default:
            if (step.data) {
                drawArrayViz({ ...step, type: 'search', comparing: -1, found: false });
            }
            break;
    }
}

function drawArrayViz(step) {
    const data = step.data;
    const n = data.length;
    const boxW = Math.min(70, (canvas.width - 100) / n);
    const boxH = 50;
    const startX = (canvas.width - n * boxW) / 2;
    const startY = canvas.height / 2 - boxH / 2;

    for (let i = 0; i < n; i++) {
        const x = startX + i * boxW;
        let color = '#1e1e2a';
        let textColor = '#a0a0b5';
        let borderColor = 'rgba(255,255,255,0.06)';

        if (step.type === 'search') {
            if (step.comparing === i) {
                color = step.found ? 'rgba(34,197,94,0.3)' : 'rgba(218,112,20,0.25)';
                borderColor = step.found ? '#22c55e' : '#DA7014';
                textColor = '#fff';
            }
        } else if (step.type === 'pair') {
            if (i === step.currentIndex) {
                color = 'rgba(218,112,20,0.25)';
                borderColor = '#DA7014';
                textColor = '#fff';
            }
            if (step.found && i === step.pairIndex) {
                color = 'rgba(34,197,94,0.3)';
                borderColor = '#22c55e';
                textColor = '#fff';
            }
        } else if (step.comparing !== undefined) {
            if (step.comparing === i) {
                color = 'rgba(218,112,20,0.25)';
                borderColor = '#DA7014';
                textColor = '#fff';
            }
        }

        drawRoundRect(ctx, x + 2, startY, boxW - 4, boxH, 6);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = textColor;
        ctx.font = '600 15px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(data[i], x + boxW / 2, startY + boxH / 2);

        ctx.fillStyle = '#6b6b80';
        ctx.font = '400 11px Inter';
        ctx.fillText(`[${i}]`, x + boxW / 2, startY + boxH + 16);
    }

    if (step.type === 'search' && step.target !== undefined) {
        ctx.fillStyle = '#DA7014';
        ctx.font = '500 13px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(`Target: ${step.target}`, canvas.width / 2, startY - 25);
    }

    if (step.type === 'pair' && step.target !== undefined) {
        ctx.fillStyle = '#DA7014';
        ctx.font = '500 13px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(`Target sum: ${step.target}`, canvas.width / 2, startY - 25);
    }

    if (step.seen && Object.keys(step.seen).length > 0) {
        const seenStr = 'Seen: {' + Object.entries(step.seen).map(([k,v]) => `${k}:${v}`).join(', ') + '}';
        ctx.fillStyle = '#a855f7';
        ctx.font = '400 12px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.fillText(seenStr, canvas.width / 2, startY + boxH + 45);
    }
}

function drawBinarySearchViz(step) {
    const data = step.data;
    const n = data.length;
    const boxW = Math.min(70, (canvas.width - 100) / n);
    const boxH = 50;
    const startX = (canvas.width - n * boxW) / 2;
    const startY = canvas.height / 2 - boxH / 2;

    ctx.fillStyle = '#DA7014';
    ctx.font = '500 13px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(`Target: ${step.target}`, canvas.width / 2, startY - 40);

    for (let i = 0; i < n; i++) {
        const x = startX + i * boxW;
        let color = '#1e1e2a';
        let textColor = '#a0a0b5';
        let borderColor = 'rgba(255,255,255,0.06)';

        if (step.left <= i && i <= step.right) {
            color = 'rgba(218,112,20,0.1)';
            borderColor = 'rgba(218,112,20,0.3)';
        }

        if (step.found && i === step.mid) {
            color = 'rgba(34,197,94,0.3)';
            borderColor = '#22c55e';
            textColor = '#fff';
        } else if (i === step.mid) {
            color = 'rgba(245,158,11,0.2)';
            borderColor = '#f59e0b';
            textColor = '#fff';
        } else if (i === step.left) {
            color = 'rgba(34,197,94,0.15)';
            borderColor = '#22c55e';
            textColor = '#22c55e';
        } else if (i === step.right) {
            color = 'rgba(239,68,68,0.15)';
            borderColor = '#ef4444';
            textColor = '#ef4444';
        }

        drawRoundRect(ctx, x + 2, startY, boxW - 4, boxH, 6);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = textColor;
        ctx.font = '600 15px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(data[i], x + boxW / 2, startY + boxH / 2);

        ctx.fillStyle = '#6b6b80';
        ctx.font = '400 11px Inter';
        ctx.fillText(`[${i}]`, x + boxW / 2, startY + boxH + 16);
    }

    if (step.mid >= 0) {
        const midX = startX + step.mid * boxW + boxW / 2;
        ctx.fillStyle = '#f59e0b';
        ctx.font = '600 11px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('mid', midX, startY - 20);
    }

    if (step.left >= 0) {
        const leftX = startX + step.left * boxW + boxW / 2;
        ctx.fillStyle = '#22c55e';
        ctx.font = '600 11px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('left', leftX, startY - 20);
    }

    if (step.right >= 0) {
        const rightX = startX + step.right * boxW + boxW / 2;
        ctx.fillStyle = '#ef4444';
        ctx.font = '600 11px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('right', rightX, startY - 20);
    }
}

function drawSortViz(step) {
    const data = step.data;
    const n = data.length;
    const maxVal = Math.max(...data);
    const boxW = Math.min(60, (canvas.width - 80) / n);
    const maxH = canvas.height - 120;
    const startX = (canvas.width - n * boxW) / 2;
    const baseY = canvas.height - 50;

    for (let i = 0; i < n; i++) {
        const h = (data[i] / maxVal) * maxH;
        const x = startX + i * boxW;
        let color = '#DA7014';
        let borderColor = 'rgba(255,255,255,0.1)';

        if (step.sorted && step.sorted.includes(i)) {
            color = '#22c55e';
            borderColor = '#22c55e';
        }
        if (step.comparing && step.comparing.includes(i)) {
            color = '#f59e0b';
            borderColor = '#f59e0b';
        }
        if (step.swapping && step.swapping.includes(i)) {
            color = '#ef4444';
            borderColor = '#ef4444';
        }
        if (step.inserting === i || step.inserted === i) {
            color = '#a855f7';
            borderColor = '#a855f7';
        }
        if (step.currentMin === i) {
            color = '#3b82f6';
            borderColor = '#3b82f6';
        }
        if (step.pivot === i) {
            color = '#ec4899';
            borderColor = '#ec4899';
        }
        if (step.pivotFinal === i) {
            color = '#22c55e';
            borderColor = '#22c55e';
        }

        drawRoundRect(ctx, x + 3, baseY - h, boxW - 6, h, 4);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#fff';
        ctx.font = '600 12px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(data[i], x + boxW / 2, baseY - h - 5);

        ctx.fillStyle = '#6b6b80';
        ctx.font = '400 10px Inter';
        ctx.textBaseline = 'top';
        ctx.fillText(`[${i}]`, x + boxW / 2, baseY + 6);
    }

    if (step.range) {
        const [l, m, r] = step.range;
        const lx = startX + l * boxW + boxW / 2;
        const mx = startX + (m + 1) * boxW;
        const rx = startX + r * boxW + boxW / 2;

        ctx.strokeStyle = 'rgba(168,85,247,0.4)';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(lx, 15);
        ctx.lineTo(rx + boxW / 2, 15);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = '#a855f7';
        ctx.font = '400 10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('left', lx, 10);
        ctx.fillText('mid', mx, 10);
        ctx.fillText('right', rx, 10);
    }
}

function drawTreeViz(step) {
    const cx = canvas.width / 2;
    const nodeR = 22;
    const depth = step.depth || 0;
    const y = 60 + depth * 70;
    const x = cx + (Math.random() - 0.5) * (canvas.width * 0.6 / (depth + 1));

    ctx.beginPath();
    ctx.arc(cx, y, nodeR, 0, Math.PI * 2);
    ctx.fillStyle = step.val !== null ? 'rgba(34,197,94,0.2)' : 'rgba(99,102,241,0.15)';
    ctx.fill();
    ctx.strokeStyle = step.val !== null ? '#22c55e' : '#6366f1';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = '#fff';
    ctx.font = '600 13px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(step.node, cx, y);

    ctx.fillStyle = '#a0a0b5';
    ctx.font = '400 11px Inter';
    ctx.fillText(step.val !== null ? `= ${step.val}` : '', cx, y + nodeR + 15);
}

function drawLinkedListViz(step) {
    const prevData = step.prevData || [];
    const currData = step.data || [];
    const nodeW = 60;
    const nodeH = 36;
    const gap = 30;

    const drawNode = (val, x, y, color, label) => {
        drawRoundRect(ctx, x, y, nodeW, nodeH, 8);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = '#fff';
        ctx.font = '600 13px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(val, x + nodeW / 2, y + nodeH / 2);

        if (label) {
            ctx.fillStyle = '#6b6b80';
            ctx.font = '400 10px Inter';
            ctx.fillText(label, x + nodeW / 2, y + nodeH + 14);
        }
    };

    const drawArrow = (x1, y1, x2, y2) => {
        ctx.strokeStyle = '#DA7014';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        const angle = Math.atan2(y2 - y1, x2 - x1);
        ctx.beginPath();
        ctx.moveTo(x2, y2);
        ctx.lineTo(x2 - 8 * Math.cos(angle - 0.4), y2 - 8 * Math.sin(angle - 0.4));
        ctx.moveTo(x2, y2);
        ctx.lineTo(x2 - 8 * Math.cos(angle + 0.4), y2 - 8 * Math.sin(angle + 0.4));
        ctx.stroke();
    };

    if (prevData.length > 0) {
        ctx.fillStyle = '#22c55e';
        ctx.font = '500 12px Inter';
        ctx.textAlign = 'left';
        ctx.fillText('Reversed:', 30, 50);

        const prevStartX = 30;
        for (let i = 0; i < prevData.length; i++) {
            const nx = prevStartX + i * (nodeW + gap);
            drawNode(prevData[i], nx, 65, 'rgba(34,197,94,0.15)', i === 0 ? 'prev' : '');
            if (i < prevData.length - 1) {
                drawArrow(nx + nodeW, 65 + nodeH / 2, nx + nodeW + gap, 65 + nodeH / 2);
            }
        }
    }

    ctx.fillStyle = '#DA7014';
    ctx.font = '500 12px Inter';
    ctx.textAlign = 'left';
    ctx.fillText('Current:', 30, 150);

    if (currData.length > 0) {
        const currStartX = 30;
        for (let i = 0; i < currData.length; i++) {
            const nx = currStartX + i * (nodeW + gap);
            const color = i === step.currentIdx ? 'rgba(218,112,20,0.25)' : 'rgba(30,30,42,0.9)';
            drawNode(currData[i], nx, 165, color, i === 0 ? 'curr' : '');
            if (i < currData.length - 1) {
                drawArrow(nx + nodeW, 165 + nodeH / 2, nx + nodeW + gap, 165 + nodeH / 2);
            }
        }
    } else {
        ctx.fillStyle = '#6b6b80';
        ctx.font = '400 13px Inter';
        ctx.textAlign = 'left';
        ctx.fillText('null (empty)', 30, 185);
    }
}

function drawGraphViz(step) {
    const nodes = step.nodes;
    const edges = step.edges;
    const visited = new Set(step.visited);
    const nodeR = 22;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2 - 10;
    const radius = Math.min(cx, cy) - 50;

    const positions = {};
    nodes.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
        positions[n] = {
            x: cx + radius * Math.cos(angle),
            y: cy + radius * Math.sin(angle)
        };
    });

    edges.forEach(([a, b]) => {
        const pa = positions[a];
        const pb = positions[b];
        ctx.strokeStyle = visited.has(a) && visited.has(b)
            ? 'rgba(34,197,94,0.3)' : 'rgba(255,255,255,0.08)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
    });

    nodes.forEach(n => {
        const p = positions[n];
        let color = 'rgba(30,30,42,0.9)';
        let border = 'rgba(255,255,255,0.1)';
        let textColor = '#a0a0b5';

        if (n === step.current) {
            color = 'rgba(218,112,20,0.25)';
            border = '#DA7014';
            textColor = '#fff';
        } else if (visited.has(n)) {
            color = 'rgba(34,197,94,0.15)';
            border = '#22c55e';
            textColor = '#22c55e';
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, nodeR, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = border;
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = textColor;
        ctx.font = '600 13px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(n, p.x, p.y);
    });

    if (step.queue && step.queue.length > 0) {
        ctx.fillStyle = '#a0a0b5';
        ctx.font = '400 12px Inter';
        ctx.textAlign = 'left';
        ctx.fillText(`Queue/Stack: [${step.queue.join(', ')}]`, 20, canvas.height - 20);
    }
}

function drawBinaryViz(step) {
    const cx = canvas.width / 2;
    const bits = step.bits;
    const boxW = 50;
    const boxH = 50;
    const startX = cx - (bits.length * boxW) / 2;
    const y = 100;

    ctx.fillStyle = '#DA7014';
    ctx.font = '500 14px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(`Value: ${step.value}`, cx, y - 30);

    for (let i = 0; i < bits.length; i++) {
        const x = startX + i * boxW;
        drawRoundRect(ctx, x + 2, y, boxW - 4, boxH, 6);
        ctx.fillStyle = bits[i] === 1 ? 'rgba(218,112,20,0.2)' : 'rgba(30,30,42,0.9)';
        ctx.fill();
        ctx.strokeStyle = bits[i] === 1 ? '#DA7014' : 'rgba(255,255,255,0.06)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = bits[i] === 1 ? '#fff' : '#6b6b80';
        ctx.font = '600 18px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(bits[i], x + boxW / 2, y + boxH / 2);

        ctx.fillStyle = '#6b6b80';
        ctx.font = '400 10px Inter';
        ctx.fillText(`2^${bits.length - 1 - i}`, x + boxW / 2, y + boxH + 15);
    }

    if (step.nm1bits) {
        const nm1y = y + 100;
        ctx.fillStyle = '#a855f7';
        ctx.font = '500 13px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(`${step.value} & ${step.value - 1} = ${step.andResult}`, cx, nm1y - 20);

        const nm1StartX = cx - (step.nm1bits.length * boxW) / 2;
        for (let i = 0; i < step.nm1bits.length; i++) {
            const x = nm1StartX + i * boxW;
            drawRoundRect(ctx, x + 2, nm1y, boxW - 4, boxH, 6);
            ctx.fillStyle = step.nm1bits[i] === 1 ? 'rgba(168,85,247,0.2)' : 'rgba(30,30,42,0.9)';
            ctx.fill();
            ctx.strokeStyle = step.nm1bits[i] === 1 ? '#a855f7' : 'rgba(255,255,255,0.06)';
            ctx.lineWidth = 1;
            ctx.stroke();

            ctx.fillStyle = step.nm1bits[i] === 1 ? '#fff' : '#6b6b80';
            ctx.font = '600 18px JetBrains Mono';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(step.nm1bits[i], x + boxW / 2, nm1y + boxH / 2);
        }
    }

    if (step.isPower !== undefined) {
        const resultY = step.nm1bits ? y + 210 : y + 90;
        ctx.fillStyle = step.isPower ? '#22c55e' : '#ef4444';
        ctx.font = '700 18px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(step.isPower ? `${step.value} IS a power of 2 ✓` : `${step.value} is NOT a power of 2 ✗`, cx, resultY);
    }
}

function drawRoundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

function populateBrowseGrid() {
    const grid = document.getElementById('algorithmGrid');
    grid.innerHTML = algorithms.map(algo => `
        <div class="algo-card" onclick="showResult(algorithms.find(a => a.id === '${algo.id}'))">
            <div class="algo-card-icon">${vizTypes[algo.vizType]?.icon || '📊'}</div>
            <div class="algo-card-info">
                <h4>${algo.name}</h4>
                <p>${algo.category} · ${algo.difficulty}</p>
            </div>
        </div>
    `).join('');
}

populateBrowseGrid();
drawInitialVisualization(algorithms[0]);
