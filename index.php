<?php
/**
 * ShionMusicBot — landing page (MPA dashboard home).
 */

require_once __DIR__ . '/inc/ui.php';

$st = sh_web_status();
$fresh = ($st !== null && (time() - (int) ($st['ts'] ?? 0)) < 90);
$bot = sh_env('BOT_USERNAME', 'ShionMusicBot');

sh_header('index', 'Home');
?>

<section class="hero">
  <div class="disc"><?php echo sh_icon('music', 40); ?></div>
  <h1>Stream music &amp; video <b>straight into Telegram</b> voice chats</h1>
  <p>
    ShionMusicBot pipes YouTube audio and video into group voice chats with a smart
    queue, looping, seeking and live playback controls — powered by the Testweb3
    streaming engine and PyTgCalls v3.
  </p>
  <div class="cta">
    <a class="btn btn-telegram btn-lg" href="https://t.me/<?php echo sh_h($bot); ?>?startgroup=true" target="_blank" rel="noopener">
      <?php echo sh_icon('play', 14); ?> Add to your group
    </a>
    <a class="btn btn-lg" href="status.php"><?php echo sh_icon('pulse', 15); ?> Live status</a>
    <a class="btn btn-lg" href="webstream.php"><?php echo sh_icon('headphones', 15); ?> Web player</a>
  </div>
</section>

<section class="grid g4 mb">
  <div class="card stat"><div class="num"><?php echo $fresh ? (int) ($st['chats'] ?? 0) : '—'; ?></div><div class="lbl">Chats served</div></div>
  <div class="card stat"><div class="num"><?php echo $fresh ? (int) ($st['plays'] ?? 0) : '—'; ?></div><div class="lbl">Tracks played</div></div>
  <div class="card stat"><div class="num"><?php echo $fresh ? count((array) ($st['active_calls'] ?? array())) : '—'; ?></div><div class="lbl">Live streams</div></div>
  <div class="card stat"><div class="num"><?php echo $fresh ? sh_uptime($st['uptime'] ?? 0) : '—'; ?></div><div class="lbl">Uptime</div></div>
</section>

<section class="grid g3">
  <div class="card feature">
    <div class="fico"><?php echo sh_icon('search', 19); ?></div>
    <h3>Single-source search</h3>
    <p>Every lookup and stream resolves exclusively through the Testweb3 proxy — no
      yt-dlp scraping, no IP blocks, no rate limits.</p>
  </div>
  <div class="card feature">
    <div class="fico"><?php echo sh_icon('film', 19); ?></div>
    <h3>Audio &amp; video</h3>
    <p><code>/play</code> for music, <code>/vplay</code> for video. Force-play variants jump
      the queue instantly.</p>
  </div>
  <div class="card feature">
    <div class="fico"><?php echo sh_icon('queue', 19); ?></div>
    <h3>Smart queue</h3>
    <p>Per-chat queues up to 20 tracks with looping, seeking, skipping and inline
      playback buttons under every now-playing message.</p>
  </div>
  <div class="card feature">
    <div class="fico"><?php echo sh_icon('database', 19); ?></div>
    <h3>Zero-DB architecture</h3>
    <p>A high-speed in-memory state engine with full MongoDB-style interface — no
      external database cluster to pay for or babysit.</p>
  </div>
  <div class="card feature">
    <div class="fico"><?php echo sh_icon('globe', 19); ?></div>
    <h3>Multilingual</h3>
    <p>English and हिन्दी out of the box, switchable per chat with <code>/lang</code>
      or the settings panel.</p>
  </div>
  <div class="card feature">
    <div class="fico"><?php echo sh_icon('shield', 19); ?></div>
    <h3>Admin toolkit</h3>
    <p>Auth users, sudoers, chat blacklists, global broadcasts and a live web
      dashboard with real-time metrics.</p>
  </div>
</section>

<?php sh_footer(); ?>
