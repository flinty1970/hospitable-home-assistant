"""Validate the shipped blueprint and examples against HA's real schemas."""

from pathlib import Path

from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.util import yaml as yaml_util


async def test_heating_blueprint(hass):
    data = yaml_util.parse_yaml(
        await hass.async_add_executor_job(
            Path("blueprints/automation/occupancy_heating.yaml").read_text
        )
    )
    blueprint = Blueprint(data, schema=BLUEPRINT_SCHEMA, expected_domain="automation")
    instance = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": "synthetic.yaml",
                "input": {
                    "occupied": "binary_sensor.synthetic_occupied",
                    "next_reservation": "sensor.synthetic_next",
                    "thermostat": "climate.synthetic_thermostat",
                },
            }
        },
    )
    instance.validate()
    config = instance.async_substitute()
    assert await async_validate_config_item(hass, "automation", config)


async def test_automation_examples(hass):
    data = yaml_util.parse_yaml(
        await hass.async_add_executor_job(Path("examples/automations.yaml").read_text)
    )
    for config in data:
        assert await async_validate_config_item(hass, "automation", config)
