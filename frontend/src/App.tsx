import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  BookHeart,
  BookOpen,
  Feather,
  Menu,
  MessageCircleMore,
  Plus,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { cn } from "./lib/utils";

type Mode = "chat" | "resumo";
type Message = { role: "user" | "assistant"; content: string };

const API_URL = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

const starters = [
  { icon: BookOpen, title: "Minha próxima leitura", text: "Me indique um livro para quem gostou de Torto Arado." },
  { icon: Feather, title: "Converse sobre uma obra", text: "Quero conversar sobre os temas de Dom Casmurro." },
  { icon: Sparkles, title: "Explore novos gêneros", text: "Quais livros são bons para começar a ler ficção científica?" },
];

async function request<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "Não foi possível conectar ao servidor. Confirme se o backend está rodando na porta 8000.",
    );
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Não foi possível falar com a biblioteca agora.");
  return data as T;
}

export default function App() {
  const [mode, setMode] = useState<Mode>("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function switchMode(next: Mode) {
    setMode(next);
    setError("");
    setMenuOpen(false);
  }

  async function sendChat(text = message) {
    const clean = text.trim();
    if (!clean || loading) return;
    const history = messages;
    setMessages((current) => [...current, { role: "user", content: clean }]);
    setMessage("");
    setError("");
    setLoading(true);
    try {
      const data = await request<{ reply: string }>("/chat", { message: clean, history });
      setMessages((current) => [...current, { role: "assistant", content: data.reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Algo deu errado. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  async function createSummary(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || loading) return;
    const label = author.trim() ? `${title.trim()}, de ${author.trim()}` : title.trim();
    const userMessage = `Resuma “${label}”`;
    setMessages((current) => [...current, { role: "user", content: userMessage }]);
    setError("");
    setLoading(true);
    try {
      const data = await request<{ resumo: string }>("/resumo", {
        titulo: title.trim(),
        autor: author.trim() || null,
      });
      setMessages((current) => [...current, { role: "assistant", content: data.resumo }]);
      setTitle("");
      setAuthor("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Algo deu errado. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  function onChatKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendChat();
    }
  }

  function newConversation() {
    setMessages([]);
    setError("");
    setMessage("");
    setTitle("");
    setAuthor("");
    setMenuOpen(false);
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <button className="brand" onClick={newConversation} aria-label="Ir para o início">
          <span className="brand__mark"><BookHeart size={23} strokeWidth={1.8} /></span>
          <span>entrelinhas</span>
        </button>
        <nav className={cn("nav", menuOpen && "nav--open")} aria-label="Navegação principal">
          <button className={cn("nav__link", mode === "chat" && "nav__link--active")} onClick={() => switchMode("chat")}>
            Conversar
          </button>
          <button className={cn("nav__link", mode === "resumo" && "nav__link--active")} onClick={() => switchMode("resumo")}>
            Resumir livro
          </button>
          <Button variant="outline" className="new-chat" onClick={newConversation}>
            <Plus size={16} /> Nova conversa
          </Button>
        </nav>
        <button className="menu-button" onClick={() => setMenuOpen((v) => !v)} aria-label="Abrir menu">
          {menuOpen ? <X /> : <Menu />}
        </button>
      </header>

      <main className={cn("main", messages.length > 0 && "main--conversation")}>
        {messages.length === 0 ? (
          <section className="welcome">
            <div className="eyebrow"><Sparkles size={14} /> Curadoria literária com IA</div>
            <h1>{mode === "chat" ? <>Toda boa conversa<br />começa com um <em>livro.</em></> : <>Um livro inteiro,<br /><em>em poucos minutos.</em></>}</h1>
            <p className="intro">
              {mode === "chat"
                ? "Descubra histórias, explore ideias e encontre sua próxima leitura em uma conversa feita para quem ama livros."
                : "Digite uma obra e receba uma visão clara da sinopse, temas centrais e do leitor para quem ela é indicada."}
            </p>

            {mode === "chat" ? (
              <>
                <div className="prompt-box">
                  <Textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={onChatKeyDown}
                    placeholder="Pergunte sobre livros, autores ou peça uma recomendação..."
                    aria-label="Sua mensagem"
                    rows={2}
                  />
                  <div className="prompt-box__footer">
                    <span><MessageCircleMore size={15} /> Conversa literária</span>
                    <Button size="icon" onClick={() => void sendChat()} disabled={!message.trim() || loading} aria-label="Enviar">
                      <ArrowUp size={19} />
                    </Button>
                  </div>
                </div>
                <div className="starters">
                  {starters.map(({ icon: Icon, title: itemTitle, text }) => (
                    <button className="starter" key={itemTitle} onClick={() => void sendChat(text)}>
                      <span className="starter__icon"><Icon size={19} /></span>
                      <span><strong>{itemTitle}</strong><small>{text}</small></span>
                      <ArrowUp className="starter__arrow" size={16} />
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <form className="summary-card" onSubmit={createSummary}>
                <div className="summary-card__heading">
                  <span><Search size={20} /></span>
                  <div><strong>Qual livro você quer explorar?</strong><small>O autor é opcional, mas ajuda a encontrar a obra certa.</small></div>
                </div>
                <label>
                  Título do livro
                  <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex.: Cem anos de solidão" autoFocus />
                </label>
                <label>
                  Autor <span>(opcional)</span>
                  <Input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Ex.: Gabriel García Márquez" />
                </label>
                <Button type="submit" disabled={!title.trim() || loading}>
                  <Sparkles size={17} /> Criar resumo
                </Button>
              </form>
            )}
          </section>
        ) : (
          <section className="conversation">
            <div className="conversation__top">
              <div><span>{mode === "chat" ? "Conversa literária" : "Resumo de livro"}</span><h2>{mode === "chat" ? "Entre livros e ideias" : "Sua leitura essencial"}</h2></div>
              <Button variant="ghost" onClick={newConversation}><Plus size={16} /> Recomeçar</Button>
            </div>
            <div className="messages" aria-live="polite">
              {messages.map((item, index) => (
                <article className={cn("message", `message--${item.role}`)} key={`${item.role}-${index}`}>
                  <div className="message__avatar">
                    {item.role === "assistant" ? <BookHeart size={18} /> : "V"}
                  </div>
                  <div className="message__body">
                    <span>{item.role === "assistant" ? "Entrelinhas" : "Você"}</span>
                    {item.role === "assistant" ? (
                      <div className="message__content message__content--markdown">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            a: ({ children, ...props }) => (
                              <a {...props} target="_blank" rel="noreferrer">
                                {children}
                              </a>
                            ),
                          }}
                        >
                          {item.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="message__content">{item.content}</p>
                    )}
                  </div>
                </article>
              ))}
              {loading && (
                <article className="message message--assistant">
                  <div className="message__avatar"><BookHeart size={18} /></div>
                  <div className="message__body"><span>Entrelinhas</span><div className="typing"><i /><i /><i /></div></div>
                </article>
              )}
              {error && <div className="error">{error}</div>}
              <div ref={endRef} />
            </div>
            {mode === "chat" ? (
              <div className="composer">
                <Textarea value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={onChatKeyDown} placeholder="Continue a conversa..." rows={1} />
                <Button size="icon" onClick={() => void sendChat()} disabled={!message.trim() || loading}><ArrowUp size={19} /></Button>
              </div>
            ) : (
              <form className="summary-inline" onSubmit={createSummary}>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Outro título..." />
                <Input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Autor (opcional)" />
                <Button type="submit" disabled={!title.trim() || loading}><Sparkles size={16} /> Resumir</Button>
              </form>
            )}
            <small className="disclaimer">A IA pode cometer erros. Confirme informações importantes na edição da obra.</small>
          </section>
        )}
      </main>

      {messages.length === 0 && <footer><span>Feito para leitores curiosos.</span><span>Entrelinhas · 2026</span></footer>}
    </div>
  );
}
