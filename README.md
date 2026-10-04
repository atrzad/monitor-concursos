# Monitor de editais

Toda manhã (8h) consulta o MCP da pciconcursos e manda um e-mail dizendo se o concurso monitorado apareceu. Se o computador estiver desligado às 8h, roda assim que ele ligar e você fizer login. Quando aparece uma novidade, também manda uma notificação na área de trabalho.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `monitor.py` | o script (só Python padrão, sem dependências) |
| `~/.config/monitor-concursos/config.toml` | e-mail + concursos monitorados (permissão 600) |
| `~/.local/state/monitor-concursos/estado.json` | ids já vistos, para marcar o que é "NOVO" |
| `~/.config/systemd/user/monitor-concursos.{service,timer}` | o agendamento |

## Configurar o e-mail (uma vez)

1. Ative a verificação em 2 etapas na conta Google.
2. Gere uma senha de app em https://myaccount.google.com/apppasswords.
3. Cole a senha em `senha_app` no arquivo `~/.config/monitor-concursos/config.toml`.

## Comandos

```sh
./monitor.py --dry-run                                  # testa e mostra o e-mail, sem enviar
systemctl --user start monitor-concursos.service        # roda agora e envia o e-mail
systemctl --user list-timers monitor-concursos.timer    # próxima execução
journalctl --user -u monitor-concursos.service -n 20    # log
systemctl --user disable --now monitor-concursos.timer  # desliga o monitor
```

Para rodar mesmo sem login (com o computador ligado): `sudo loginctl enable-linger $USER`.

## Monitorar outro concurso

Acrescente um bloco no `config.toml`:

```toml
[[monitor]]
nome = "Caixa — Técnico Bancário"
termos = ["Caixa Econômica"]
padrao = "caixa economica"
```

`padrao` é uma regex aplicada ao título do concurso e ao da notícia, em minúsculas e sem acentos. Deixe o padrão específico: a busca por "Banco do Brasil" também devolve "Marinha do Brasil", e é o padrão que filtra isso.
