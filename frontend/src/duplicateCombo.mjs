async function readJson(response, fallback) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : fallback);
  return data;
}

async function listCombos(fetcher) {
  const data = await readJson(await fetcher('/api/combos'), 'Failed to load combos');
  if (!Array.isArray(data.combos)) throw new Error('Invalid combo list');
  return data.combos;
}

export async function duplicateCombo(name, fetcher, customName = null) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const combos = await listCombos(fetcher);
    const source = combos.find(c => c.name.toLowerCase() === name.toLowerCase());
    if (!source) throw new Error('Source combo no longer exists');
    const names = new Set(combos.map(c => c.name.toLowerCase()));
    const base = customName || `${source.name}-copy`;
    let candidate = base;
    for (let n = 2; names.has(candidate.toLowerCase()); n++) candidate = `${base}-${n}`;
    const payload = { name: candidate, strategy: source.strategy, models: [...source.models] };
    const response = await fetcher('/api/combos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (response.status === 409) continue;
    const data = await readJson(response, 'Failed to duplicate combo');
    if (!data.success || data.combo?.name !== candidate) throw new Error('Invalid create response');
    const saved = (await listCombos(fetcher)).find(c => c.name === candidate);
    if (!saved || saved.strategy !== payload.strategy || JSON.stringify(saved.models) !== JSON.stringify(payload.models)) {
      throw new Error('Duplicate could not be verified; refresh before retrying');
    }
    return saved;
  }
  throw new Error('Combo names changed repeatedly; please try again');
}