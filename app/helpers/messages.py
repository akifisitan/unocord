import nextcord
import logging

logger = logging.getLogger(__name__)


async def log_error_message(
    context: (
        nextcord.Interaction | nextcord.Message | nextcord.TextChannel | nextcord.User
    ),
    error_message: str,
) -> None:
    """Sends an error message to the logging channel.
    Parameters
    ----------
    context:
        the context to use to find the logging channel
    error_message:
        the error message to send
    """
    embed = nextcord.Embed(
        description=error_message, color=0xFF0000, timestamp=nextcord.utils.utcnow()
    )
    logging_channel = nextcord.utils.get(context.guild.channels, name="logs")
    if not logging_channel:
        logging.error(f'Could not find logging channel "logs"')
        return
    try:
        await logging_channel.send(content=f"", embed=embed)
    except Exception as e:
        logging.error(f"Could not send error message to the logging channel: {e}")


async def delete_message(
    message: nextcord.Message, delay: int = None, log: bool = False
) -> bool:
    """Deletes a message.
    Parameters
    ----------
    message:
        the message to delete
    delay:
        (Optional) how long to wait before deleting the message (seconds)
    log:
        (Optional) whether to send potential error messages to the log channel
    Returns
    -------
    bool:
        True if the message was successfully deleted, False otherwise
    """
    try:
        await message.delete(delay=delay)
        return True
    except nextcord.Forbidden:
        logging.error(
            f'Bot is missing the "Manage Messages" permission in channel #{message.channel}'
        )
        if log:
            await log_error_message(
                context=message,
                error_message=f'**Bot is missing the "Manage Messages" permission in '
                f"{message.channel.mention}**",
            )
    except nextcord.NotFound:
        pass
    except Exception as e:
        logging.error(f"Error deleting message: {e}")
        if log:
            await log_error_message(
                context=message, error_message=f"**Could not delete message: {e}**"
            )
    return False


async def send_message(
    channel: nextcord.TextChannel | nextcord.Thread,
    content: str = None,
    embed: nextcord.Embed = None,
    view: nextcord.ui.View = None,
    delete_after: float = None,
    log: bool = False,
) -> bool:
    """Sends a message to a channel, returns True if successful, False otherwise.
    Parameters
    ----------
    channel: nextcord.TextChannel
        the channel to send the message to
    content: str
        (Optional) the content of the message
    embed:
        (Optional) the embed to send
    view:
        (Optional) the view to send
    delete_after: float
        (Optional) how long to wait before deleting the message
    log:
        (Optional) whether to send potential error messages to the log channel
    Returns
    -------
    bool
        True if sending the message was successful, False otherwise
    """
    try:
        await channel.send(
            content=content, embed=embed, view=view, delete_after=delete_after
        )
        return True
    except nextcord.Forbidden:
        logging.error(
            f'Bot is missing the "Send Messages" permission in channel #{channel}'
        )
        if log:
            await log_error_message(
                channel,
                f'**Bot is missing the "Send Messages" permission in {channel.mention}**',
            )
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        if log:
            await log_error_message(channel, f"**Could not send message: {e}**")
    return False


async def send_private_message(
    user: nextcord.User,
    content: str = None,
    embed: nextcord.Embed = None,
    file: nextcord.File = None,
) -> bool:
    """Sends a private message to a user, returns True if successful, False otherwise.
    Parameters
    ----------
    user: nextcord.User
        the user to send the DM to
    content: str
        (Optional) the content of the message
    embed:
        (Optional) the embed to send
    file:
        (Optional) the file to send
    Returns
    -------
    bool
        True if sending the private was successful, False otherwise
    """
    try:
        await user.send(content=content, embed=embed, file=file)
        return True
    except nextcord.Forbidden:
        logging.error(f"User {user} has DMs disabled.")
    except Exception as e:
        logging.error(f"COULD NOT SEND DM: {e}")
    return False


async def reply_to_message(
    message: nextcord.Message, content: str, log: bool = True
) -> bool:
    """Replies to a message ignoring any errors
    Parameters
    ----------
    message:
        the message to reply to
    content:
        the content of the message
    log:
        (Optional) whether to send potential error messages to the log channel
    Returns
    -------
    bool
        True if replying to the message was successful, False otherwise
    """
    try:
        await message.reply(content=content)
        return True
    except Exception as e:
        if log:
            await log_error_message(
                context=message, error_message=f"**Could not reply to message: {e}**"
            )
        logging.error(e)
    return False


async def edit_message(
    message: nextcord.Message,
    content: str = None,
    embed: nextcord.Embed = None,
    view: nextcord.ui.View = None,
) -> bool:
    """Edits a message.
    Parameters
    ----------
    message:
        the message to edit
    content: str
        (Optional) the content of the message
    embed:
        (Optional) the embed to send
    view:
        (Optional) the view to send
    Returns
    -------
    bool
        True if editing the message was successful, False otherwise
    """
    try:
        await message.edit(content=content, embed=embed, view=view)
        return True
    except nextcord.HTTPException:
        pass
    return False
