# Clippa

Clippa transforma um roteiro em vídeo narrado — voz neural, legenda sincronizada
e imagens à sua escolha — pronto para Reels, Stories, TikTok ou YouTube.

- **App:** https://clippa-633789634558.southamerica-east1.run.app
- **Landing page:** https://clippa-nine.vercel.app
- **Motor:** este repositório (fork de [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)), rodando no Google Cloud Run (região São Paulo)

## Como usar

1. Abra o app e, na primeira vez, clique em **⚙** e cole sua chave de acesso.
2. Escreva o **roteiro** — o texto exatamente como deve ser narrado.
3. Descreva os **temas visuais** (guiam a busca de imagens no banco Pexels) — pode escrever em português, ex.: `mãos contando dinheiro, livro aberto sendo lido de perto`. O Clippa traduz automaticamente antes de buscar.
4. Escolha **voz**, **formato** (9:16 / 16:9 / 1:1), **posição/cor da legenda** e **trilha sonora**.
5. Clique em **Gerar vídeo** e aguarde (1–3 minutos).
6. **Baixe o vídeo** assim que terminar — ele não fica guardado no servidor.

## Dicas para um resultado melhor

- Termos visuais **específicos** evitam clipes de desenho/3D no lugar de fotografia real (a tradução automática não resolve isso — a especificidade é sua).
- Narração em português roda a ~150 palavras/minuto — calcule o roteiro pela duração desejada.
- Evite frases muito curtas após vírgula — a legenda quebra por frase e pode isolar fragmentos.
- **Legenda centralizada** é mais segura para Reels/Stories — no rodapé, fica atrás da UI do Instagram.

## Limitações

- **Cold-start:** sem uso recente, o próximo pedido pode levar alguns segundos a mais para começar (a instância "acorda").
- **Armazenamento efêmero:** vídeos gerados não persistem entre reinícios do servidor.

## Para quem for mexer no código

Ver `~/.claude/skills/video-factory/SKILL.md` (documentação completa do motor, API,
deploy e arquitetura) e `render.yaml` (blueprint de deploy). Roadmap de produto
(contas, login social, fontes de imagem) descrito à parte.
