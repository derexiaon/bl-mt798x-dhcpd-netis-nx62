// SPDX-License-Identifier: GPL-2.0+

#include <command.h>
#include <dm/ofnode.h>

#ifdef CONFIG_MTD_LAYOUT_SPI_NAND
extern const char *mtd_layout_spi_nand_replace(const char *str, char *buf,
					       size_t bufsz);
#endif

static int do_showlayout(struct cmd_tbl *cmdtp, int flag, int argc, char *const argv[])
{
    ofnode node, layout;

    node = ofnode_path("/mtd-layout");

    if (ofnode_valid(node) && ofnode_get_child_count(node)) {
        ofnode_for_each_subnode(layout, node) {
            const char *ids = ofnode_read_string(layout, "mtdids");
            const char *parts = ofnode_read_string(layout, "mtdparts");

#ifdef CONFIG_MTD_LAYOUT_SPI_NAND
            char ids_buf[256], parts_buf[512];
            ids = mtd_layout_spi_nand_replace(ids, ids_buf,
					       sizeof(ids_buf));
            parts = mtd_layout_spi_nand_replace(parts, parts_buf,
						 sizeof(parts_buf));
#endif
            printf("mtd label: %s, mtdids: %s, mtdparts: %s\n", 
                ofnode_read_string(layout, "label"),
                ids,
                parts);
        }
    } else {
        printf("get mtd layout failed!\n");
    }

    return CMD_RET_SUCCESS;
}

U_BOOT_CMD(
	showlayout, 2, 0, do_showlayout,
	"Show mtd layout",
	""
);
