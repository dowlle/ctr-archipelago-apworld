from ..generic.Rules import add_rule
from .Options import ctrAPOptions
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld


def set_rules(world: "ctrAPWorld"):
    self = world.multiworld
    player = world.player
    options = world.options

    # N. Sanity Beach
    add_rule(self.get_entrance("Crash Cove Warp Pad", player),
            lambda state: state.can_reach("N. Sanity Beach", "Adventure Mode", player))
    add_rule(self.get_entrance("Roo's Tubes Warp Pad", player),
             lambda state: state.can_reach("N. Sanity Beach", "Adventure Mode", player))
    add_rule(self.get_entrance("Mystery Caves Warp Pad", player),
             lambda state: state.can_reach("N. Sanity Beach", "Adventure Mode", player))    
    add_rule(self.get_entrance("Sewer Speedway Warp Pad", player),
             lambda state: state.can_reach("N. Sanity Beach", "Adventure Mode", player))
    add_rule(self.get_entrance("Ripper Roo Garage Door", player),
             lambda state: state.can_reach("N. Sanity Beach", "Adventure Mode", player))
    add_rule(self.get_entrance("Skull Rock Warp Pad", player),
             lambda state: state.can_reach("N. Sanity Beach", "Adventure Mode", player))

    # Crash Cove
    add_rule(self.get_location("Crash Cove: Trophy Race", player),
             lambda state: state.has("Trophy", player, 0))
    add_rule(self.get_location("Crash Cove: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Crash Cove: Trophy Race", player))
    add_rule(self.get_location("Crash Cove: Gold Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Crash Cove: Trophy Race", player))
    add_rule(self.get_location("Crash Cove: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Crash Cove: Trophy Race", player))
    add_rule(self.get_location("Crash Cove: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Crash Cove: Trophy Race", player))
    
    # Roo's Tubes
    add_rule(self.get_location("Roo's Tubes: Trophy Race", player),
             lambda state: state.has("Trophy", player, 0))
    add_rule(self.get_location("Roo's Tubes: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Roo's Tubes: Trophy Race", player))
    add_rule(self.get_location("Roo's Tubes: Gold Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Roo's Tubes: Trophy Race", player))
    add_rule(self.get_location("Roo's Tubes: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Roo's Tubes: Trophy Race", player))
    add_rule(self.get_location("Roo's Tubes: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Roo's Tubes: Trophy Race", player))
    
    # Mystery Caves
    add_rule(self.get_location("Mystery Caves: Trophy Race", player),
             lambda state: state.has("Trophy", player, 1))
    add_rule(self.get_location("Mystery Caves: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Mystery Caves: Trophy Race", player))
    add_rule(self.get_location("Mystery Caves: Gold Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Mystery Caves: Trophy Race", player))
    add_rule(self.get_location("Mystery Caves: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Mystery Caves: Trophy Race", player))
    add_rule(self.get_location("Mystery Caves: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Mystery Caves: Trophy Race", player))

    # Sewer Speedway
    add_rule(self.get_location("Sewer Speedway: Trophy Race", player),
             lambda state: state.has("Trophy", player, 2))
    add_rule(self.get_location("Sewer Speedway: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Sewer Speedway: Trophy Race", player))
    add_rule(self.get_location("Sewer Speedway: Gold Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Sewer Speedway: Trophy Race", player))
    add_rule(self.get_location("Sewer Speedway: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Sewer Speedway: Trophy Race", player))
    add_rule(self.get_location("Sewer Speedway: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 1) and state.can_reach_location("Sewer Speedway: Trophy Race", player))

    # Ripper Roo's Challenge
    add_rule(self.get_location("Ripper Roo Garage: Boss Race", player),
             lambda state: state.has("Trophy", player, 4))
    
    # Skull Rock
    add_rule(self.get_location("Skull Rock: Crystal Bonus Round", player),
             lambda state: state.has("Key", player, 1))
    

    # Transition N. Sanity Beach - > Lost Ruins
    add_rule(self.get_entrance("Gem Stone Valley -> Lost Ruins", player),
             lambda state: state.has("Key", player, 1))
    add_rule(self.get_entrance("N. Sanity Beach -> Gem Stone Valley", player),
             lambda state: state.has("Key", player, 1))

    # Gem Stone Valley
    add_rule(self.get_entrance("Slide Coliseum Warp Pad", player),
            lambda state: state.can_reach("Gem Stone Valley", None , player))
    add_rule(self.get_entrance("Turbo Track Warp Pad", player),
            lambda state: state.can_reach("Gem Stone Valley", None , player))
    
    add_rule(self.get_location("Slide Coliseum: Sapphire Time Trial", player),
             lambda state: state.has("Sapphire Relic", player, 8))
    add_rule(self.get_location("Slide Coliseum: Gold Time Trial", player),
             lambda state: state.has("Sapphire Relic", player, 8))
    add_rule(self.get_location("Slide Coliseum: Platinum Time Trial", player),
             lambda state: state.has("Sapphire Relic", player, 8))
    
    add_rule(self.get_location("Turbo Track: Sapphire Time Trial", player),
             lambda state: state.has("Red Gem", player, 1) and ("Green Gem", player, 1) and ("Blue Gem", player, 1) and ("Yellow Gem", player, 1) and ("Purple Gem", player, 1))
    add_rule(self.get_location("Turbo Track: Gold Time Trial", player),
             lambda state: state.has("Red Gem", player, 1) and ("Green Gem", player, 1) and ("Blue Gem", player, 1) and ("Yellow Gem", player, 1) and ("Purple Gem", player, 1))
    add_rule(self.get_location("Turbo Track: Platinum Time Trial", player),
             lambda state: state.has("Red Gem", player, 1) and ("Green Gem", player, 1) and ("Blue Gem", player, 1) and ("Yellow Gem", player, 1) and ("Purple Gem", player, 1))
    
    # Cups Room
    add_rule(self.get_entrance("Gem Stone Valley -> Cups Room", player),
             lambda state: state.has("Key", player, 2))
    add_rule(self.get_entrance("Red Cup Warp Pad", player),
             lambda state: state.can_reach("Cups Room", None, player))
    add_rule(self.get_entrance("Green Cup Warp Pad", player),
             lambda state: state.can_reach("Cups Room", None, player))
    add_rule(self.get_entrance("Blue Cup Warp Pad", player),
             lambda state: state.can_reach("Cups Room", None, player))
    add_rule(self.get_entrance("Yellow Cup Warp Pad", player),
             lambda state: state.can_reach("Cups Room", None, player))
    add_rule(self.get_entrance("Purple Cup Warp Pad", player),
             lambda state: state.can_reach("Cups Room", None, player))
    
    add_rule(self.get_location("Red Gem Cup: Gem", player),
             lambda state: state.has("Red CTR Token", player, 4))
    add_rule(self.get_location("Green Gem Cup: Gem", player),
             lambda state: state.has("Green CTR Token", player, 4))
    add_rule(self.get_location("Blue Gem Cup: Gem", player),
             lambda state: state.has("Blue CTR Token", player, 4))
    add_rule(self.get_location("Yellow Gem Cup: Gem", player),
             lambda state: state.has("Yellow CTR Token", player, 4))
    add_rule(self.get_location("Purple Gem Cup: Gem", player),
             lambda state: state.has("Purple CTR Token", player, 4))

    # N. Oxide
    add_rule(self.get_entrance("N. Oxide Garage Door", player),
            lambda state: state.can_reach("Gem Stone Valley", None , player))
    add_rule(self.get_location("N. Oxide Garage: Beat Oxide Once", player),
            lambda state: state.has("Trophy", player, 16) and state.has("Key", player, 4))
    add_rule(self.get_location("N. Oxide Garage: Beat Oxide Twice", player),
            lambda state: state.has("Sapphire Relic", player, 18) and state.can_reach_location("N. Oxide Garage: Beat Oxide Once", player))
 

    # Lost Ruins
    add_rule(self.get_entrance("Coco Park Warp Pad", player),
            lambda state: state.can_reach("Lost Ruins", None , player))
    add_rule(self.get_entrance("Tiger Temple Warp Pad", player),
             lambda state: state.can_reach("Lost Ruins", None , player))
    add_rule(self.get_entrance("Papu's Pyramid Warp Pad", player),
             lambda state: state.can_reach("Lost Ruins", None , player))    
    add_rule(self.get_entrance("Dingo Canyon Warp Pad", player),
             lambda state: state.can_reach("Lost Ruins", None , player))
    add_rule(self.get_entrance("Papu Papu Garage Door", player),
             lambda state: state.can_reach("Lost Ruins", None , player))
    add_rule(self.get_entrance("Rampage Ruins Warp Pad", player),
             lambda state: state.can_reach("Lost Ruins", None , player))

    # Coco Park
    add_rule(self.get_location("Coco Park: Trophy Race", player),
             lambda state: state.has("Trophy", player, 4))
    add_rule(self.get_location("Coco Park: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Coco Park: Trophy Race", player))
    add_rule(self.get_location("Coco Park: Gold Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Coco Park: Trophy Race", player))
    add_rule(self.get_location("Coco Park: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Coco Park: Trophy Race", player))
    add_rule(self.get_location("Coco Park: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Coco Park: Trophy Race", player))
    
    # Tiger Temple
    add_rule(self.get_location("Tiger Temple: Trophy Race", player),
             lambda state: state.has("Trophy", player, 4))
    add_rule(self.get_location("Tiger Temple: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Tiger Temple: Trophy Race", player))
    add_rule(self.get_location("Tiger Temple: Gold Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Tiger Temple: Trophy Race", player))
    add_rule(self.get_location("Tiger Temple: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Tiger Temple: Trophy Race", player))
    add_rule(self.get_location("Tiger Temple: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Tiger Temple: Trophy Race", player))
    
    # Papu's Pyramid
    add_rule(self.get_location("Papu's Pyramid: Trophy Race", player),
             lambda state: state.has("Trophy", player, 6))
    add_rule(self.get_location("Papu's Pyramid: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Papu's Pyramid: Trophy Race", player))
    add_rule(self.get_location("Papu's Pyramid: Gold Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Papu's Pyramid: Trophy Race", player))
    add_rule(self.get_location("Papu's Pyramid: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Papu's Pyramid: Trophy Race", player))
    add_rule(self.get_location("Papu's Pyramid: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Papu's Pyramid: Trophy Race", player))

    # Dingo Canyon
    add_rule(self.get_location("Dingo Canyon: Trophy Race", player),
             lambda state: state.has("Trophy", player, 7))
    add_rule(self.get_location("Dingo Canyon: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Dingo Canyon: Trophy Race", player))
    add_rule(self.get_location("Dingo Canyon: Gold Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Dingo Canyon: Trophy Race", player))
    add_rule(self.get_location("Dingo Canyon: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Dingo Canyon: Trophy Race", player))
    add_rule(self.get_location("Dingo Canyon: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 2) and state.can_reach_location("Dingo Canyon: Trophy Race", player))

    # Papu Papu's Challenge
    add_rule(self.get_location("Papu Papu Garage: Boss Race", player),
             lambda state: state.has("Trophy", player, 8))
    
    # Rampage Ruins
    add_rule(self.get_location("Rampage Ruins: Crystal Bonus Round", player),
             lambda state: state.has("Key", player, 2))
    

    # Transition Lost Ruins - > Glacier Park
    add_rule(self.get_entrance("Lost Ruins -> Glacier Park", player),
             lambda state: state.has("Key", player, 2))
    #Transition N. Sanity Beach - > Glacier Park
    add_rule(self.get_entrance("Glacier Park -> N. Sanity Beach", player),
             lambda state: state.has("Key", player, 2))


    # Glacier Park
    add_rule(self.get_entrance("Blizzard Bluff Warp Pad", player),
            lambda state: state.can_reach("Glacier Park", None , player))
    add_rule(self.get_entrance("Dragon Mines Warp Pad", player),
             lambda state: state.can_reach("Glacier Park", None , player))
    add_rule(self.get_entrance("Polar Pass Warp Pad", player),
             lambda state: state.can_reach("Glacier Park", None , player))    
    add_rule(self.get_entrance("Tiny Arena Warp Pad", player),
             lambda state: state.can_reach("Glacier Park", None , player))
    add_rule(self.get_entrance("Komodo Joe Garage Door", player),
             lambda state: state.can_reach("Glacier Park", None , player))
    add_rule(self.get_entrance("Rocky Road Warp Pad", player),
             lambda state: state.can_reach("Glacier Park", None , player))

    # Blizzard Bluff
    add_rule(self.get_location("Blizzard Bluff: Trophy Race", player),
             lambda state: state.has("Trophy", player, 8))
    add_rule(self.get_location("Blizzard Bluff: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Blizzard Bluff: Trophy Race", player))
    add_rule(self.get_location("Blizzard Bluff: Gold Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Blizzard Bluff: Trophy Race", player))
    add_rule(self.get_location("Blizzard Bluff: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Blizzard Bluff: Trophy Race", player))
    add_rule(self.get_location("Blizzard Bluff: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Blizzard Bluff: Trophy Race", player))
    
    # Dragon Mines
    add_rule(self.get_location("Dragon Mines: Trophy Race", player),
             lambda state: state.has("Trophy", player, 9))
    add_rule(self.get_location("Dragon Mines: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Dragon Mines: Trophy Race", player))
    add_rule(self.get_location("Dragon Mines: Gold Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Dragon Mines: Trophy Race", player))
    add_rule(self.get_location("Dragon Mines: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Dragon Mines: Trophy Race", player))
    add_rule(self.get_location("Dragon Mines: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Dragon Mines: Trophy Race", player))
    
    # Polar Pass
    add_rule(self.get_location("Polar Pass: Trophy Race", player),
             lambda state: state.has("Trophy", player, 10))
    add_rule(self.get_location("Polar Pass: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Polar Pass: Trophy Race", player))
    add_rule(self.get_location("Polar Pass: Gold Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Polar Pass: Trophy Race", player))
    add_rule(self.get_location("Polar Pass: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Polar Pass: Trophy Race", player))
    add_rule(self.get_location("Polar Pass: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Polar Pass: Trophy Race", player))

    # Tiny Arena
    add_rule(self.get_location("Tiny Arena: Trophy Race", player),
             lambda state: state.has("Trophy", player, 11))
    add_rule(self.get_location("Tiny Arena: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Tiny Arena: Trophy Race", player))
    add_rule(self.get_location("Tiny Arena: Gold Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Tiny Arena: Trophy Race", player))
    add_rule(self.get_location("Tiny Arena: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Tiny Arena: Trophy Race", player))
    add_rule(self.get_location("Tiny Arena: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 3) and state.can_reach_location("Tiny Arena: Trophy Race", player))

    # Komodo Joe's Challenge
    add_rule(self.get_location("Komodo Joe Garage: Boss Race", player),
             lambda state: state.has("Trophy", player, 12))
    
    # Rocky Road
    add_rule(self.get_location("Rocky Road: Crystal Bonus Round", player),
             lambda state: state.has("Key", player, 3))


    # Transition Glacier Park - > Citadel City
    add_rule(self.get_entrance("Glacier Park -> Citadel City", player),
             lambda state: state.has("Key", player, 3))


    # Citadel City
    add_rule(self.get_entrance("N. Gin Labs Warp Pad", player),
            lambda state: state.can_reach("Citadel City", None , player))
    add_rule(self.get_entrance("Cortex Castle Warp Pad", player),
             lambda state: state.can_reach("Citadel City", None , player))
    add_rule(self.get_entrance("Hot Air Skyway Warp Pad", player),
             lambda state: state.can_reach("Citadel City", None , player))    
    add_rule(self.get_entrance("Oxide Station Warp Pad", player),
             lambda state: state.can_reach("Citadel City", None , player))
    add_rule(self.get_entrance("Pinstripe Garage Door", player),
             lambda state: state.can_reach("Citadel City", None , player))
    add_rule(self.get_entrance("Nitro Court Warp Pad", player),
             lambda state: state.can_reach("Citadel City", None , player))

    # N. Gin Labs
    add_rule(self.get_location("N. Gin Labs: Trophy Race", player),
             lambda state: state.has("Trophy", player, 12))
    add_rule(self.get_location("N. Gin Labs: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("N. Gin Labs: Trophy Race", player))
    add_rule(self.get_location("N. Gin Labs: Gold Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("N. Gin Labs: Trophy Race", player))
    add_rule(self.get_location("N. Gin Labs: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("N. Gin Labs: Trophy Race", player))
    add_rule(self.get_location("N. Gin Labs: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("N. Gin Labs: Trophy Race", player))
    
    # Cortex Castle
    add_rule(self.get_location("Cortex Castle: Trophy Race", player),
             lambda state: state.has("Trophy", player, 12))
    add_rule(self.get_location("Cortex Castle: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Cortex Castle: Trophy Race", player))
    add_rule(self.get_location("Cortex Castle: Gold Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Cortex Castle: Trophy Race", player))
    add_rule(self.get_location("Cortex Castle: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Cortex Castle: Trophy Race", player))
    add_rule(self.get_location("Cortex Castle: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Cortex Castle: Trophy Race", player))
    
    # Hot Air Skyway
    add_rule(self.get_location("Hot Air Skyway: Trophy Race", player),
             lambda state: state.has("Trophy", player, 13))
    add_rule(self.get_location("Hot Air Skyway: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Hot Air Skyway: Trophy Race", player))
    add_rule(self.get_location("Hot Air Skyway: Gold Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Hot Air Skyway: Trophy Race", player))
    add_rule(self.get_location("Hot Air Skyway: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Hot Air Skyway: Trophy Race", player))
    add_rule(self.get_location("Hot Air Skyway: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Hot Air Skyway: Trophy Race", player))

    # Oxide Station
    add_rule(self.get_location("Oxide Station: Trophy Race", player),
             lambda state: state.has("Trophy", player, 14))
    add_rule(self.get_location("Oxide Station: Sapphire Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Oxide Station: Trophy Race", player))
    add_rule(self.get_location("Oxide Station: Gold Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Oxide Station: Trophy Race", player))
    add_rule(self.get_location("Oxide Station: Platinum Time Trial", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Oxide Station: Trophy Race", player))
    add_rule(self.get_location("Oxide Station: CTR Token Challenge", player),
             lambda state: state.has("Key", player, 4) and state.can_reach_location("Oxide Station: Trophy Race", player))

    # Pinstripe's Challenge
    add_rule(self.get_location("Pinstripe Garage: Boss Race", player),
             lambda state: state.has("Trophy", player, 16))
    
    # Nitro Court
    add_rule(self.get_location("Nitro Court: Crystal Bonus Round", player),
             lambda state: state.has("Key", player, 4))
