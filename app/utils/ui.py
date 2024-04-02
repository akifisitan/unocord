import nextcord


class PaginationView(nextcord.ui.View):
    def __init__(self, embed: nextcord.Embed, pages: list, timeout: int):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.embed = embed
        self.current_page = 0

    @nextcord.ui.button(label="\u200b", style=nextcord.ButtonStyle.grey, emoji="⬅️")
    async def btn_previous_page(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        self.current_page -= 1
        if self.current_page < 0:
            self.current_page = len(self.pages) - 1
        self.embed.description = self.pages[self.current_page]
        await interaction.response.edit_message(embed=self.embed, view=self)

    @nextcord.ui.button(label="\u200b", style=nextcord.ButtonStyle.grey, emoji="➡️")
    async def btn_next_page(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        self.current_page += 1
        if self.current_page > len(self.pages) - 1:
            self.current_page = 0
        self.embed.description = self.pages[self.current_page]
        await interaction.response.edit_message(embed=self.embed, view=self)


class ConfirmationView(nextcord.ui.View):
    def __init__(self, timeout: int):
        super().__init__(timeout=timeout)
        self.value = False

    @nextcord.ui.button(label="Yes", style=nextcord.ButtonStyle.green)
    async def btn_yes(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        self.value = True
        self.stop()

    @nextcord.ui.button(label="No", style=nextcord.ButtonStyle.red)
    async def btn_no(
        self, button: nextcord.ui.Button, interaction: nextcord.Interaction
    ):
        self.value = False
        self.stop()
