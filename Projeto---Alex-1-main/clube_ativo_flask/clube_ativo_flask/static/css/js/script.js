document.addEventListener('DOMContentLoaded', function () {
    // Lógica para o menu de navegação mobile (Hamburguer)
    const navToggle = document.getElementById('nav-toggle');
    const navLinks = document.getElementById('nav-links');
    const userMenu = document.querySelector('.user-menu');

    if (navToggle && navLinks) {
        navToggle.addEventListener('click', () => {
            navLinks.classList.toggle('active');
            if (userMenu) {
                // Garante que o submenu do usuário não fique aberto ao fechar o nav
                userMenu.classList.remove('active');
            }
        });
    }

    // Lógica para o submenu do usuário no mobile
    if (userMenu) {
        const userMenuTrigger = userMenu.querySelector('.user-menu-trigger');
        userMenuTrigger.addEventListener('click', (event) => {
            // Previne que o clique feche o menu principal no mobile, abrindo apenas o submenu
            if (window.innerWidth <= 768) {
                event.preventDefault();
                userMenu.classList.toggle('active');
            }
        });
    }

    // --- NOVO ---
    // Fecha o menu mobile ao clicar em um link de navegação
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        // Adiciona o evento a todos os itens que não sejam o menu do usuário
        if (!item.classList.contains('user-menu')) {
            item.addEventListener('click', () => {
                if (navLinks.classList.contains('active')) {
                    navLinks.classList.remove('active');
                }
            });
        }
    });
});
