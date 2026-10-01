<?php
/**
 * ShionMusicBot — shared UI kit: inline SVG icons, header/footer, helpers.
 * Pure vector icons — zero external CDN dependencies.
 */

require_once __DIR__ . '/../runner_lib.php';

function sh_icon(string $name, int $size = 20): string
{
    static $icons = array(
        'music'    => '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
        'play'     => '<polygon points="5 3 19 12 5 21 5 3" fill="currentColor" stroke="none"/>',
        'pause'    => '<rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/>',
        'skip'     => '<polygon points="5 4 15 12 5 20 5 4" fill="currentColor" stroke="none"/><line x1="19" y1="5" x2="19" y2="19"/>',
        'stop'     => '<rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" stroke="none"/>',
        'search'   => '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
        'pulse'    => '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
        'terminal' => '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
        'users'    => '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
        'globe'    => '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
        'shield'   => '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
        'settings' => '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.09a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
        'bot'      => '<rect x="4" y="7" width="16" height="12" rx="2"/><circle cx="9" cy="13" r="1.4" fill="currentColor" stroke="none"/><circle cx="15" cy="13" r="1.4" fill="currentColor" stroke="none"/><line x1="12" y1="7" x2="12" y2="4"/><circle cx="12" cy="3" r="1"/>',
        'headphones' => '<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><rect x="2" y="14" width="4" height="7" rx="2"/><rect x="18" y="14" width="4" height="7" rx="2"/>',
        'queue'    => '<line x1="9" y1="6" x2="21" y2="6"/><line x1="9" y1="12" x2="21" y2="12"/><line x1="9" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1.3" fill="currentColor" stroke="none"/><circle cx="4" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="4" cy="18" r="1.3" fill="currentColor" stroke="none"/>',
        'zap'      => '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill="currentColor" stroke="none"/>',
        'close'    => '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
        'download' => '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
        'clock'    => '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
        'cpu'      => '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
        'layers'   => '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
        'film'     => '<rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/>',
        'database' => '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
        'repeat'   => '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
    );

    $body = isset($icons[$name]) ? $icons[$name] : $icons['music'];
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' . $size . '" height="' . $size
        . '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        . 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' . $body . '</svg>';
}

function sh_uptime($seconds): string
{
    $seconds = (int) $seconds;
    $days = intdiv($seconds, 86400);
    $hours = intdiv($seconds % 86400, 3600);
    $minutes = intdiv($seconds % 3600, 60);
    if ($days > 0) {
        return "{$days}d {$hours}h {$minutes}m";
    }
    if ($hours > 0) {
        return "{$hours}h {$minutes}m";
    }
    return "{$minutes}m " . ($seconds % 60) . 's';
}

function sh_header(string $active, string $title, string $desc = ''): void
{
    $pages = array(
        'index'      => array('index.php', 'Home', 'music'),
        'status'     => array('status.php', 'Status', 'pulse'),
        'commands'   => array('commands.php', 'Commands', 'terminal'),
        'assistant'  => array('assistant.php', 'Assistant', 'bot'),
        'webstream'  => array('webstream.php', 'Web Player', 'headphones'),
    );
    $nav = '';
    foreach ($pages as $key => $info) {
        $cls = $key === $active ? ' class="active"' : '';
        $nav .= '<a href="' . $info[0] . '"' . $cls . '>'
            . sh_icon($info[2], 15) . '<span>' . $info[1] . '</span></a>';
    }
    $bot = sh_env('BOT_USERNAME', 'ShionMusicBot');
    echo '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        . '<meta name="viewport" content="width=device-width, initial-scale=1">'
        . '<meta name="robots" content="noindex">'
        . '<title>' . sh_h($title) . ' — ShionMusicBot</title>'
        . '<link rel="stylesheet" href="assets/style.css">'
        . '<link rel="icon" href="data:image/svg+xml,' . rawurlencode(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#7c3aed"/><path d="M9 18V5l12-2v13" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/><circle cx="6" cy="18" r="2.6" fill="#fff"/><circle cx="18" cy="16" r="2.6" fill="#fff"/></svg>'
        ) . '">'
        . '</head><body>'
        . '<header class="topbar"><div class="wrap bar-inner">'
        . '<a class="brand" href="index.php">'
        . '<span class="brand-badge">' . sh_icon('music', 17) . '</span>'
        . '<span class="brand-name">Shion<b>MusicBot</b></span></a>'
        . '<nav class="nav">' . $nav . '</nav>'
        . '<a class="btn btn-telegram" href="https://t.me/' . sh_h($bot) . '" target="_blank" rel="noopener">'
        . sh_icon('play', 13) . ' Open in Telegram</a>'
        . '</div></header>'
        . '<main class="wrap"><section class="page-head">'
        . '<h1>' . sh_h($title) . '</h1>'
        . ($desc !== '' ? '<p class="muted">' . sh_h($desc) . '</p>' : '')
        . '</section>';
}

function sh_footer(): void
{
    echo '</main><footer class="footer"><div class="wrap foot-inner">'
        . '<span>' . sh_icon('music', 14) . ' <b>ShionMusicBot</b> — Telegram music &amp; video streaming</span>'
        . '<span class="muted">Streaming engine: Testweb3 · PyTgCalls v3 · Pyrogram v2</span>'
        . '</div></footer></body></html>';
}

function sh_badge(bool $ok, string $text): string
{
    $cls = $ok ? 'ok' : 'bad';
    $dot = $ok ? '<span class="dot ok"></span>' : '<span class="dot bad"></span>';
    return '<span class="badge ' . $cls . '">' . $dot . sh_h($text) . '</span>';
}
