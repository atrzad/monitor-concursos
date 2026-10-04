#!/usr/bin/env python3
"""Monitor de editais: consulta o MCP da pciconcursos e manda um e-mail por dia
dizendo se o concurso monitorado já apareceu.

Uso:
  monitor.py              verifica e envia o e-mail
  monitor.py --dry-run    verifica e só mostra o e-mail na tela (não envia)

Config: ~/.config/monitor-concursos/config.toml  (modelo: config.example.toml)
Estado: ~/.local/state/monitor-concursos/estado.json (ids já vistos)
"""
import json
import os
import re
import smtplib
import subprocess
import sys
import time
import tomllib
import unicodedata
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

MCP_URL = "https://mcp.pciconcursos.com.br/mcp"
CONFIG = Path(os.environ.get("MONITOR_CONFIG", Path.home() / ".config/monitor-concursos/config.toml"))
ESTADO = Path.home() / ".local/state/monitor-concursos/estado.json"


def normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sem_acento.lower()


def chamar_mcp(ferramenta, argumentos, tentativas=3):
    corpo = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": ferramenta, "arguments": argumentos},
    }).encode()
    req = urllib.request.Request(MCP_URL, data=corpo, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    for n in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resposta = json.loads(r.read())
            return json.loads(resposta["result"]["content"][0]["text"])
        except Exception as e:  # rede ainda subindo, servidor fora etc.
            if n == tentativas:
                raise RuntimeError(f"{ferramenta}({argumentos}) falhou: {e}") from e
            time.sleep(60)


def verificar(monitor):
    """Devolve (data_atual do servidor, lista de concursos que batem com o padrão)."""
    padrao = re.compile(monitor["padrao"])
    achados, data_atual = {}, None
    for termo in monitor["termos"]:
        dados = chamar_mcp("pesquisar_concursos", {"termo": termo})
        data_atual = dados.get("meta", {}).get("data_atual", data_atual)
        for c in dados.get("data", []):
            alvo = normalizar(f'{c.get("titulo", "")} {c.get("noticia", {}).get("titulo", "")}')
            if padrao.search(alvo):
                achados[c["id"]] = c
    return data_atual, list(achados.values())


def descrever(c):
    d = c.get("datas", {})
    if d.get("aberto"):
        situacao = f'INSCRIÇÕES ABERTAS até {d.get("fim")} ({d.get("dias_restantes")} dias)'
    elif d.get("dias_restantes") is not None and d["dias_restantes"] < 0:
        situacao = f'inscrições encerradas em {d.get("fim")}'
    else:
        situacao = f'inscrições: {d.get("inicio") or "?"} a {d.get("fim") or "?"}'
    return (f'• {c.get("titulo")}\n'
            f'  Cargos: {c.get("cargos_resumo")} · {c.get("vagas_salario") or ""}\n'
            f'  {situacao}\n'
            f'  Notícia: {c.get("noticia", {}).get("link")}\n')


def enviar(cfg, assunto, corpo):
    em = cfg["email"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = assunto, em["usuario"], ", ".join(em["para"])
    msg.set_content(corpo)
    with smtplib.SMTP_SSL(em.get("smtp_host", "smtp.gmail.com"), em.get("smtp_port", 465), timeout=60) as s:
        s.login(em["usuario"], em["senha_app"].replace(" ", ""))
        s.send_message(msg)


def notificar(titulo, texto):
    try:
        subprocess.run(["notify-send", "-u", "critical", titulo, texto], timeout=10)
    except Exception:
        pass  # sem sessão gráfica: o e-mail já basta


def main():
    dry = "--dry-run" in sys.argv
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    hoje = datetime.now().strftime("%d/%m/%Y")

    blocos, saiu_algum, novos_total, erros = [], False, 0, []
    for m in cfg["monitor"]:
        try:
            data_srv, achados = verificar(m)
        except Exception as e:
            erros.append(f'{m["nome"]}: {e}')
            blocos.append(f'## {m["nome"]}\n⚠ Não consegui verificar hoje: {e}\n')
            continue
        vistos = set(estado.get(m["nome"], []))
        novos = [c for c in achados if str(c["id"]) not in vistos]
        if achados:
            saiu_algum = True
            novos_total += len(novos)
            cab = f'## {m["nome"]}: SAIU ✅' + (f' ({len(novos)} novidade(s) desde ontem)' if novos else '')
            blocos.append(cab + "\n" + "\n".join(descrever(c) for c in achados))
        else:
            blocos.append(f'## {m["nome"]}: ainda não saiu ❌\n'
                          f'Nenhum concurso com "{m["padrao"]}" na pciconcursos (data do servidor: {data_srv}).\n')
        estado[m["nome"]] = sorted(vistos | {str(c["id"]) for c in achados})

    if erros and not saiu_algum:
        assunto = f"[Monitor de editais] ⚠ Não consegui verificar — {hoje}"
    elif saiu_algum:
        assunto = f"[Monitor de editais] ✅ SAIU{' (NOVO!)' if novos_total else ''} — {hoje}"
    else:
        assunto = f"[Monitor de editais] Ainda não saiu — {hoje}"
    corpo = (f"Verificação diária de {hoje} (fonte: MCP pciconcursos).\n\n" + "\n".join(blocos) +
             "\n—\nEnviado por ~/Projects/monitor-concursos · para parar: "
             "systemctl --user disable --now monitor-concursos.timer\n")

    if dry:
        print(f"Assunto: {assunto}\n\n{corpo}")
        return
    if not cfg["email"].get("senha_app", "").strip():
        notificar("Monitor de editais", f"Falta a senha de app do Gmail em {CONFIG}. Resultado de hoje: {assunto}")
        sys.exit(f"Sem senha_app em {CONFIG}; e-mail não enviado. Resultado: {assunto}")
    enviar(cfg, assunto, corpo)
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2))
    if novos_total:
        notificar("Edital publicado!", "Veja o e-mail do Monitor de editais.")
    print(f"E-mail enviado: {assunto}")


if __name__ == "__main__":
    main()
