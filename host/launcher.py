import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from host.app import main
    main()
