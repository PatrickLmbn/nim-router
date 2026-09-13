import React from 'react';

import nvidiaLight from '../../icons/NVIDIA_light_dark/NVIDIA_light.svg';
import nvidiaDark from '../../icons/NVIDIA_light_dark/NVIDIA_dark.svg';
import groqLight from '../../icons/Groq_wordmark_light_dark/Groq_wordmark_light.svg';
import groqDark from '../../icons/Groq_wordmark_light_dark/Groq_wordmark_dark.svg';
import cerebrasLight from '../../icons/Cerebras_wordmark_light_dark/Cerebras_wordmark_light.svg';
import cerebrasDark from '../../icons/Cerebras_wordmark_light_dark/Cerebras_wordmark_dark.svg';
import openrouterLight from '../../icons/OpenRouter_light_dark/OpenRouter_light.svg';
import openrouterDark from '../../icons/OpenRouter_light_dark/OpenRouter_dark.svg';
import opencodeLight from '../../icons/OpenCode_light_dark/OpenCode_light.svg';
import opencodeDark from '../../icons/OpenCode_light_dark/OpenCode_dark.svg';
import baiSvg from '../../icons/b.ai.svg';

export function resolveProvider(input) {
  if (!input) return 'NVIDIA';
  const str = String(input).trim().toLowerCase();

  for (const prefix of ['[nvidia] ', '[openrouter] ', '[opencode] ', '[groq] ', '[cerebras] ', '[bai] ', '[category] ']) {
    if (str.startsWith(prefix)) return resolveProvider(str.slice(prefix.length).trim());
  }

  if (str === 'bai' || str === 'b.ai' || str.startsWith('bai/') || str.includes('b.ai') || str === 'glm-5.3-flash' || str === 'qwen3.8-flash' || str === 'hy3') {
    return 'BAI';
  }
  if (str === 'openrouter' || str.startsWith('openrouter/') || str.endsWith(':free') || str.includes('openrouter')) {
    return 'OpenRouter';
  }
  if (str === 'opencode' || str.startsWith('opencode/') || str.endsWith('-free') || str.includes('opencode')) {
    return 'OpenCode';
  }
  if (str === 'groq' || str.startsWith('groq/') || str.includes('versatile') || str.includes('instant') || str.includes('specdec') || str.includes('mixtral-8x7b') || str.includes('gemma2-') || str.includes('llama3-') || str.startsWith('qwen/')) {
    return 'Groq';
  }
  if (str === 'cerebras' || str.startsWith('cerebras/') || str.includes('cerebras') || str.includes('llama3.1') || str.includes('csk') || str === 'gpt-oss-120b' || str === 'qwen-3.8-27b' || str === 'gemma-4-31b') {
    return 'Cerebras';
  }
  return 'NVIDIA';
}

const providerIcons = {
  NVIDIA: { light: nvidiaLight, dark: nvidiaDark, name: 'NVIDIA' },
  Groq: { light: groqLight, dark: groqDark, name: 'Groq' },
  Cerebras: { light: cerebrasLight, dark: cerebrasDark, name: 'Cerebras' },
  OpenRouter: { light: openrouterLight, dark: openrouterDark, name: 'OpenRouter' },
  OpenCode: { light: opencodeLight, dark: opencodeDark, name: 'OpenCode' },
  BAI: { light: baiSvg, dark: baiSvg, name: 'B.AI', isSingle: true }
};

export function ModelIcon({ model, provider, className = "h-4 w-auto max-h-4" }) {
  const provKey = resolveProvider(provider || model);
  const iconData = providerIcons[provKey] || providerIcons.NVIDIA;

  if (iconData.isSingle) {
    return (
      <img
        src={iconData.light}
        alt={iconData.name}
        className={`${className} object-contain dark:invert select-none pointer-events-none transition-all duration-200`}
      />
    );
  }

  return (
    <span className="inline-flex items-center justify-center shrink-0">
      <img
        src={iconData.light}
        alt={iconData.name}
        className={`${className} object-contain dark:hidden block select-none pointer-events-none transition-all duration-200`}
      />
      <img
        src={iconData.dark}
        alt={iconData.name}
        className={`${className} object-contain dark:block hidden select-none pointer-events-none transition-all duration-200`}
      />
    </span>
  );
}

export function ProviderIcon({ provider, model, className = "h-4 w-auto max-h-4" }) {
  return <ModelIcon model={model} provider={provider} className={className} />;
}
