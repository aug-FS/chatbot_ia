import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, BookHeart, BookOpen, Feather, LogOut, Menu, MessageCircleMore, Plus, Search, Sparkles, Trash2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { cn } from "./lib/utils";

type Mode = "chat" | "resumo";
type Message = { role: "user" | "assistant"; content: string };
type User = { id: number; name: string; email: string };
type Conversation = { id: number; title: string; mode: Mode; updated_at: string };
type AuthData = { token: string; user: User };

const API_URL = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const TOKEN_KEY = "entrelinhas_token";
const starters = [
  { icon: BookOpen, title: "Minha próxima leitura", text: "Me indique um livro para quem gostou de Torto Arado." },
  { icon: Feather, title: "Converse sobre uma obra", text: "Quero conversar sobre os temas de Dom Casmurro." },
  { icon: Sparkles, title: "Explore novos gêneros", text: "Quais livros são bons para começar a ler ficção científica?" },
];

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  }).catch(() => { throw new Error("Não foi possível conectar ao servidor."); });
  const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) localStorage.removeItem(TOKEN_KEY);
    throw new Error(data.detail || "Não foi possível concluir a operação.");
  }
  return data as T;
}

function AuthScreen({ onAuth }: { onAuth: (data: AuthData) => void }) {
  const [registering, setRegistering] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const data = await api<AuthData>(registering ? "/auth/register" : "/auth/login", {
        method: "POST", body: JSON.stringify({ ...(registering ? { name } : {}), email, password }),
      });
      localStorage.setItem(TOKEN_KEY, data.token); onAuth(data);
    } catch (err) { setError(err instanceof Error ? err.message : "Não foi possível entrar."); }
    finally { setLoading(false); }
  }

  return <div className="auth-page">
    <section className="auth-brand"><span className="brand__mark"><BookHeart size={28} /></span><h1>entrelinhas</h1><p>Seu espaço para descobrir, conversar e guardar boas histórias.</p></section>
    <form className="auth-card" onSubmit={submit}>
      <div><span className="eyebrow"><Sparkles size={13} /> Biblioteca pessoal</span><h2>{registering ? "Crie sua conta" : "Que bom ter você de volta"}</h2><p>{registering ? "Comece sua coleção de conversas literárias." : "Entre para continuar suas conversas."}</p></div>
      {registering && <label>Nome<Input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} autoComplete="name" /></label>}
      <label>E-mail<Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></label>
      <label>Senha<Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete={registering ? "new-password" : "current-password"} /></label>
      {error && <div className="error">{error}</div>}
      <Button type="submit" disabled={loading}>{loading ? "Aguarde..." : registering ? "Criar conta" : "Entrar"}</Button>
      <button type="button" className="auth-switch" onClick={() => { setRegistering(!registering); setError(""); }}>{registering ? "Já tenho uma conta" : "Ainda não tenho uma conta"}</button>
    </form>
  </div>;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [mode, setMode] = useState<Mode>("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [message, setMessage] = useState(""); const [title, setTitle] = useState(""); const [author, setAuthor] = useState("");
  const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false); const [historyOpen, setHistoryOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  async function loadConversations() { setConversations(await api<Conversation[]>("/conversations")); }
  useEffect(() => { const token = localStorage.getItem(TOKEN_KEY); if (!token) { setAuthLoading(false); return; } api<User>("/auth/me").then((value) => { setUser(value); return loadConversations(); }).catch(() => localStorage.removeItem(TOKEN_KEY)).finally(() => setAuthLoading(false)); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  function newConversation(nextMode: Mode = mode) { setMode(nextMode); setMessages([]); setConversationId(null); setMessage(""); setTitle(""); setAuthor(""); setError(""); setHistoryOpen(false); }
  async function openConversation(item: Conversation) { setLoading(true); setError(""); try { const data = await api<Conversation & { messages: Message[] }>(`/conversations/${item.id}`); setConversationId(item.id); setMode(item.mode); setMessages(data.messages); setHistoryOpen(false); } catch (err) { setError(err instanceof Error ? err.message : "Erro ao abrir conversa."); } finally { setLoading(false); } }
  async function removeConversation(event: React.MouseEvent, id: number) { event.stopPropagation(); await api(`/conversations/${id}`, { method: "DELETE" }); if (conversationId === id) newConversation(); await loadConversations(); }
  function logout() { localStorage.removeItem(TOKEN_KEY); setUser(null); setConversations([]); newConversation(); }

  async function sendChat(text = message) {
    const clean = text.trim(); if (!clean || loading) return;
    setMessages((current) => [...current, { role: "user", content: clean }]); setMessage(""); setError(""); setLoading(true);
    try { const data = await api<{ reply: string; conversation_id: number }>("/chat", { method: "POST", body: JSON.stringify({ message: clean, conversation_id: conversationId }) }); setConversationId(data.conversation_id); setMessages((current) => [...current, { role: "assistant", content: data.reply }]); await loadConversations(); }
    catch (err) { setError(err instanceof Error ? err.message : "Algo deu errado."); } finally { setLoading(false); }
  }
  async function createSummary(event: FormEvent) {
    event.preventDefault(); if (!title.trim() || loading) return;
    const label = author.trim() ? `${title.trim()}, de ${author.trim()}` : title.trim(); setMessages((current) => [...current, { role: "user", content: `Resuma “${label}”` }]); setError(""); setLoading(true);
    try { const data = await api<{ resumo: string; conversation_id: number }>("/resumo", { method: "POST", body: JSON.stringify({ titulo: title.trim(), autor: author.trim() || null, conversation_id: conversationId }) }); setConversationId(data.conversation_id); setMessages((current) => [...current, { role: "assistant", content: data.resumo }]); setTitle(""); setAuthor(""); await loadConversations(); }
    catch (err) { setError(err instanceof Error ? err.message : "Algo deu errado."); } finally { setLoading(false); }
  }
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendChat(); } }
  if (authLoading) return <div className="page-loading"><BookHeart /><span>Preparando sua biblioteca...</span></div>;
  if (!user) return <AuthScreen onAuth={(data) => { setUser(data.user); void loadConversations(); }} />;

  return <div className="app-shell">
    <header className="site-header"><button className="brand" onClick={() => newConversation()}><span className="brand__mark"><BookHeart size={23} /></span><span>entrelinhas</span></button>
      <nav className={cn("nav", menuOpen && "nav--open")}><button className={cn("nav__link", mode === "chat" && "nav__link--active")} onClick={() => newConversation("chat")}>Conversar</button><button className={cn("nav__link", mode === "resumo" && "nav__link--active")} onClick={() => newConversation("resumo")}>Resumir livro</button><Button variant="outline" onClick={() => setHistoryOpen(!historyOpen)}><BookOpen size={16} /> Histórico</Button><div className="user-menu"><span>{user.name}</span><button onClick={logout} title="Sair"><LogOut size={17} /></button></div></nav>
      <button className="menu-button" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X /> : <Menu />}</button></header>
    <div className="workspace">
      <aside className={cn("history", historyOpen && "history--open")}><div className="history__top"><div><small>Minha biblioteca</small><h3>Conversas</h3></div><button onClick={() => setHistoryOpen(false)}><X size={18} /></button></div><Button onClick={() => newConversation()}><Plus size={16} /> Nova conversa</Button><div className="history__list">{conversations.length === 0 && <p>Suas conversas aparecerão aqui.</p>}{conversations.map((item) => <button className={cn("history__item", item.id === conversationId && "history__item--active")} onClick={() => void openConversation(item)} key={item.id}><span>{item.mode === "chat" ? <MessageCircleMore size={15} /> : <Sparkles size={15} />}<strong>{item.title}</strong><small>{new Date(item.updated_at).toLocaleDateString("pt-BR")}</small></span><i onClick={(event) => void removeConversation(event, item.id)}><Trash2 size={14} /></i></button>)}</div></aside>
      <main className={cn("main", messages.length > 0 && "main--conversation")}>
        {messages.length === 0 ? <section className="welcome"><div className="eyebrow"><Sparkles size={14} /> Curadoria literária com IA</div><h1>{mode === "chat" ? <>Toda boa conversa<br />começa com um <em>livro.</em></> : <>Um livro inteiro,<br /><em>em poucos minutos.</em></>}</h1><p className="intro">{mode === "chat" ? "Descubra histórias, explore ideias e guarde cada conversa na sua biblioteca." : "Receba uma visão clara da sinopse, temas centrais e do leitor indicado."}</p>
          {mode === "chat" ? <><div className="prompt-box"><Textarea value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={onKeyDown} placeholder="Pergunte sobre livros, autores ou peça uma recomendação..." rows={2} /><div className="prompt-box__footer"><span><MessageCircleMore size={15} /> Conversa literária</span><Button size="icon" onClick={() => void sendChat()} disabled={!message.trim() || loading}><ArrowUp size={19} /></Button></div></div><div className="starters">{starters.map(({ icon: Icon, title: itemTitle, text }) => <button className="starter" key={itemTitle} onClick={() => void sendChat(text)}><span className="starter__icon"><Icon size={19} /></span><span><strong>{itemTitle}</strong><small>{text}</small></span><ArrowUp className="starter__arrow" size={16} /></button>)}</div></> : <SummaryForm title={title} author={author} setTitle={setTitle} setAuthor={setAuthor} submit={createSummary} loading={loading} />}
        </section> : <section className="conversation"><div className="conversation__top"><div><span>{mode === "chat" ? "Conversa literária" : "Resumo de livro"}</span><h2>{mode === "chat" ? "Entre livros e ideias" : "Sua leitura essencial"}</h2></div><Button variant="ghost" onClick={() => newConversation()}><Plus size={16} /> Recomeçar</Button></div><div className="messages">{messages.map((item, index) => <article className={cn("message", `message--${item.role}`)} key={`${item.role}-${index}`}><div className="message__avatar">{item.role === "assistant" ? <BookHeart size={18} /> : user.name.charAt(0).toUpperCase()}</div><div className="message__body"><span>{item.role === "assistant" ? "Entrelinhas" : "Você"}</span>{item.role === "assistant" ? <div className="message__content message__content--markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown></div> : <p className="message__content">{item.content}</p>}</div></article>)}{loading && <article className="message message--assistant"><div className="message__avatar"><BookHeart size={18} /></div><div className="typing"><i /><i /><i /></div></article>}{error && <div className="error">{error}</div>}<div ref={endRef} /></div>{mode === "chat" ? <div className="composer"><Textarea value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={onKeyDown} placeholder="Continue a conversa..." rows={1} /><Button size="icon" onClick={() => void sendChat()} disabled={!message.trim() || loading}><ArrowUp size={19} /></Button></div> : <form className="summary-inline" onSubmit={createSummary}><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Outro título..." /><Input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Autor (opcional)" /><Button type="submit" disabled={!title.trim() || loading}>Resumir</Button></form>}<small className="disclaimer">A IA pode cometer erros. Confirme informações importantes.</small></section>}
      </main>
    </div>
  </div>;
}

function SummaryForm({ title, author, setTitle, setAuthor, submit, loading }: { title: string; author: string; setTitle: (v: string) => void; setAuthor: (v: string) => void; submit: (e: FormEvent) => void; loading: boolean }) {
  return <form className="summary-card" onSubmit={submit}><div className="summary-card__heading"><span><Search size={20} /></span><div><strong>Qual livro você quer explorar?</strong><small>O autor é opcional.</small></div></div><label>Título<Input value={title} onChange={(e) => setTitle(e.target.value)} required /></label><label>Autor <span>(opcional)</span><Input value={author} onChange={(e) => setAuthor(e.target.value)} /></label><Button type="submit" disabled={!title.trim() || loading}><Sparkles size={17} /> Criar resumo</Button></form>;
}
