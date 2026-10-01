<?php
/**
 * ShionMusicBot — command explorer with live filtering.
 */

require_once __DIR__ . '/inc/ui.php';

$commands = array(
    array('Streaming', 'music', array(
        array('/play', '<name or link>', 'Stream audio into the voice chat', 'Everyone'),
        array('/vplay', '<name or link>', 'Stream video into the voice chat', 'Everyone'),
        array('/playforce', '<name or link>', 'Clear queue & play this track now', 'Everyone'),
        array('/vplayforce', '<name or link>', 'Video variant of force play', 'Everyone'),
        array('/pause', '', 'Pause the current stream', 'Admin / Auth'),
        array('/resume', '', 'Resume a paused stream', 'Admin / Auth'),
        array('/stop', '', 'Stop playback and clear the queue', 'Admin / Auth'),
        array('/end', '', 'Alias of /stop', 'Admin / Auth'),
        array('/skip', '', 'Skip to the next queued track', 'Admin / Auth'),
        array('/seek', '<1:30>', 'Jump to a position in the track', 'Admin / Auth'),
        array('/volume', '<0-200>', 'Change the stream volume', 'Admin / Auth'),
    )),
    array('Queue', 'queue', array(
        array('/queue', '', 'Show the current queue', 'Everyone'),
        array('/queue', 'clear', 'Empty the queue (keeps the track playing)', 'Admin / Auth'),
        array('/shuffle', '', 'Shuffle the queued tracks', 'Admin / Auth'),
        array('/loop', '<n | off>', 'Repeat the current track n times', 'Admin / Auth'),
    )),
    array('Info', 'terminal', array(
        array('/start', '', 'Welcome message & quick links', 'Everyone'),
        array('/help', '', 'Full command reference', 'Everyone'),
        array('/settings', '', 'Language & auto-delete options', 'Everyone'),
        array('/lang', '<en | hi>', 'Switch the chat language', 'Admin'),
        array('/ping', '', 'Latency, uptime & PyTgCalls health', 'Everyone'),
        array('/alive', '', 'Alias of /ping', 'Everyone'),
        array('/stats', '', 'Resource & playback metrics', 'Everyone'),
        array('/id', '', 'Show chat and user ids', 'Everyone'),
    )),
    array('Admin', 'shield', array(
        array('/auth', '<reply | id | @user>', 'Delegate playback rights', 'Chat admin'),
        array('/unauth', '<reply | id | @user>', 'Revoke playback rights', 'Chat admin'),
        array('/authusers', '', 'List authorised users', 'Everyone'),
    )),
    array('Owner & sudo', 'users', array(
        array('/addsudo', '<reply | id | @user>', 'Promote a user to sudo', 'Owner'),
        array('/delsudo', '<reply | id | @user>', 'Demote a sudo user', 'Owner'),
        array('/sudolist', '', 'List sudo users', 'Owner'),
        array('/blacklistchat', '<id | in group>', 'Blacklist a chat', 'Sudo'),
        array('/whitelistchat', '<id | in group>', 'Whitelist a chat', 'Sudo'),
        array('/blacklistedchats', '', 'List blacklisted chats', 'Sudo'),
        array('/broadcast', '<reply>', 'Broadcast the replied message', 'Owner'),
        array('/restart', '', 'Restart the bot process', 'Owner'),
        array('/logs', '', 'Tail the bot log', 'Owner'),
        array('/exec', '<python>', 'Run a debug snippet', 'Owner'),
    )),
);

sh_header('commands', 'Command Explorer', 'Every command Shion understands — filter by name or browse by category.');
?>

<div class="searchbox">
  <input id="q" type="search" placeholder="Filter commands… (e.g. play, queue, sudo)" autocomplete="off">
</div>

<div class="row mb" id="cats">
  <button class="btn btn-ghost active" data-cat="all">All</button>
  <?php foreach ($commands as $group) {
      echo '<button class="btn btn-ghost" data-cat="' . sh_h($group[0]) . '">'
          . sh_icon($group[1], 14) . ' ' . sh_h($group[0]) . '</button>';
  } ?>
</div>

<?php foreach ($commands as $group) { ?>
<section class="card mb cat" data-cat="<?php echo sh_h($group[0]); ?>">
  <h3><?php echo sh_icon($group[1], 17); ?> <?php echo sh_h($group[0]); ?></h3>
  <table>
    <thead><tr><th>Command</th><th>Arguments</th><th>Description</th><th>Access</th></tr></thead>
    <tbody>
      <?php foreach ($group[2] as $cmd) { ?>
      <tr class="cmd">
        <td><code><?php echo sh_h($cmd[0]); ?></code></td>
        <td class="mono muted"><?php echo sh_h($cmd[1]); ?></td>
        <td><?php echo sh_h($cmd[2]); ?></td>
        <td class="muted"><?php echo sh_h($cmd[3]); ?></td>
      </tr>
      <?php } ?>
    </tbody>
  </table>
</section>
<?php } ?>

<script>
(function () {
  var input = document.getElementById('q');
  var sections = document.querySelectorAll('section.cat');
  var buttons = document.querySelectorAll('#cats button');
  var active = 'all';

  function apply() {
    var needle = input.value.trim().toLowerCase();
    sections.forEach(function (sec) {
      var catOk = active === 'all' || sec.dataset.cat === active;
      var visible = 0;
      sec.querySelectorAll('tr.cmd').forEach(function (row) {
        var hit = !needle || row.textContent.toLowerCase().indexOf(needle) !== -1;
        row.style.display = hit ? '' : 'none';
        if (hit) visible++;
      });
      sec.style.display = catOk && visible ? '' : 'none';
    });
  }

  input.addEventListener('input', apply);
  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      buttons.forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      active = btn.dataset.cat;
      apply();
    });
  });
})();
</script>

<?php sh_footer(); ?>
